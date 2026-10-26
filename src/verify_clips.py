"""
verify_clips.py - check every saved fall clip with Gemini and show the result in the dashboard.

For each injury event that has a clip in output/clips:
  - takes the fall moment (middle of the clip) and frames before/after it
  - asks Gemini: is this a real fall? whose shirt number is it? what happened?
  - stores the answer through the backend (PATCH /events/{id}/gemini), so the
    dashboard shows "Gemini: real fall / false alarm? / unsure", the jersey Gemini
    read, a description and the reason
  - a confident jersey read fills in "Unidentified" players (never overrides a staff pick)

False alarms are only MARKED by default (red "Gemini: false alarm?" badge), never deleted.
Add --remove-false-alarms to delete the ones Gemini is very sure about.

The backend must be running. Run from the src folder:
    python verify_clips.py                    every event not checked yet
    python verify_clips.py --recheck          every event, even ones already checked
    python verify_clips.py --event 412 415    only these events
    python verify_clips.py --match 35         only one match
    python verify_clips.py --dry-run          ask Gemini but save nothing
"""

import argparse
import os
import sys
import time

import cv2

import gemini_verifier as gv

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
CLIPS_DIR = os.path.join(PROJECT_ROOT, "output", "clips")

FALL_POSITION = 0.5       # clips are 3 s before + 3 s after the fall, so the fall is in the middle
SEQUENCE_FRAMES = 6       # frames before/after the fall sent with it
MAX_WIDTH = 960


# ============================================
# CLIP -> IMAGES
# ============================================

def _count_frames(path):
    cap = cv2.VideoCapture(path)
    n = 0
    while cap.isOpened() and cap.grab():
        n += 1
    cap.release()
    return n


def _read_frames(path, wanted):
    """Reads only the frame numbers in `wanted` (WebM files often report a wrong frame count)."""
    wanted = set(wanted)
    out = {}
    cap = cv2.VideoCapture(path)
    i = 0
    while cap.isOpened() and len(out) < len(wanted):
        if not cap.grab():
            break
        if i in wanted:
            ok, img = cap.retrieve()
            if ok:
                if img.shape[1] > MAX_WIDTH:
                    scale = MAX_WIDTH / img.shape[1]
                    img = cv2.resize(img, (MAX_WIDTH, int(img.shape[0] * scale)))
                out[i] = img
        i += 1
    cap.release()
    return out


def clip_images(path):
    """[(label, jpeg bytes), ...] or [] when the clip can't be read."""
    n = _count_frames(path)
    if n == 0:
        return []

    fall = min(n - 1, int(n * FALL_POSITION))

    if n <= SEQUENCE_FRAMES + 1:
        seq = list(range(n))
    else:
        step = (n - 1) / float(SEQUENCE_FRAMES - 1)
        seq = sorted({int(round(k * step)) for k in range(SEQUENCE_FRAMES)} - {fall})

    frames = _read_frames(path, seq + [fall])
    images = []

    if fall in frames:
        data = gv._jpeg(frames[fall])
        if data:
            images.append(("Image 1 - the FALL MOMENT (middle of the clip):", data))

    for k, idx in enumerate(seq, start=1):
        if idx in frames:
            data = gv._jpeg(frames[idx])
            if data:
                when = "before the fall" if idx < fall else "after the fall"
                images.append((f"Sequence frame {k}/{len(seq)} ({when}):", data))

    return images


# ============================================
# PROMPT (saved clips have the detector's overlays drawn on them)
# ============================================

def prompt_for(ev, teams):
    track = f"PLAYER T{ev.track_id}" if ev.track_id is not None else None
    name = ev.player.name if ev.player is not None else None

    who = []
    if track:
        who.append(f'the label "{track}"')
    if name:
        who.append(f'the name "{name}" (accents may be missing)')
    who_text = " or ".join(who) if who else "the player marked by the detector"

    return f"""You are verifying an automatic fall detector on football (soccer) broadcast footage.
These images come from the clip the detector saved. The detector drew its own overlays on the video:
skeleton/pose lines, and above each player a white label such as "PLAYER T12" or a player name.
The flagged player has {who_text} above them, and orange/red "REGION: ..." and "RISK: ..." text under that label
at the fall moment. The detector said: {ev.event_type}, body area {ev.region or 'unknown'}, risk {ev.risk or 'unknown'}.
Image 1 is the fall moment; the other images are in time order.

Decide:
1. real_fall: true if the flagged player is genuinely on the ground from a fall, tackle, collision or injury.
   false for a FALSE ALARM: player upright/running/jumping, bending or tying boots, celebrating, a routine
   intentional slide or dive where the player immediately gets up, a referee / coach / ball boy / spectator,
   the wrong person flagged, a replay/close-up/crowd shot, or nothing visibly wrong. If unclear, use low confidence.
2. confidence: 0.0-1.0 for that judgment (below 0.6 when unclear).
3. jersey_number: the flagged player's shirt number ONLY if clearly readable on the shirt (not from the overlay
   labels), else null. Never guess.
4. jersey_confidence: 0.0-1.0 for the number read (0 if null).
5. team: the flagged player's team from [{", ".join(teams) or "unknown"}] judged from kit colours, else null.
6. description: one short sentence describing what happens to the player.
7. reason: one short sentence explaining your real_fall decision.

Reply with JSON only:
{{"real_fall": true, "confidence": 0.0, "jersey_number": null, "jersey_confidence": 0.0, "team": null, "description": "", "reason": ""}}"""


# ============================================
# MAIN
# ============================================

def main():
    ap = argparse.ArgumentParser(description="Check saved fall clips with Gemini and store the result for the dashboard.")
    ap.add_argument("--event", type=int, nargs="+", help="only these event ids")
    ap.add_argument("--match", type=int, help="only events of this match id")
    ap.add_argument("--recheck", action="store_true", help="also check events Gemini already checked")
    ap.add_argument("--remove-false-alarms", action="store_true",
                    help=f"delete events Gemini is at least {gv.FALSE_ALARM_CONFIDENCE:.0%} sure are not falls")
    ap.add_argument("--min-jersey-confidence", type=float, default=gv.JERSEY_CONFIDENCE,
                    help="how sure Gemini must be of a shirt number before it changes the player (default %(default)s)")
    ap.add_argument("--delay", type=float, default=4.0, help="seconds between Gemini requests (free keys are rate limited)")
    ap.add_argument("--limit", type=int, help="stop after this many clips")
    ap.add_argument("--dry-run", action="store_true", help="ask Gemini and print, but save nothing")
    args = ap.parse_args()

    if not gv.init():
        sys.exit("Gemini is not available. Put GEMINI_API_KEY in your .env file (pip install google-genai).")

    if not args.dry_run:
        try:
            gv.requests.get(gv.API_BASE + "/docs", timeout=5)
        except Exception:
            sys.exit(f"The backend is not reachable at {gv.API_BASE}. Start it first (uvicorn main:app).")

    from database import SessionLocal
    from models import InjuryEvent

    teams = gv.team_names()

    db = SessionLocal()
    q = db.query(InjuryEvent).filter(InjuryEvent.clip_path.isnot(None))
    if args.event:
        q = q.filter(InjuryEvent.id.in_(args.event))
    events = q.order_by(InjuryEvent.id).all()
    if args.match is not None:
        events = [e for e in events if e.match_session_id == args.match]   # encrypted: filtered in Python
    if not args.recheck and not args.event:
        # gemini_verdict is encrypted: filtered in Python
        events = [e for e in events if e.gemini_verdict in (None, "error")]

    if args.limit:
        events = events[: args.limit]

    print(f"[VERIFY] {len(events)} event(s) to check | clips folder: {CLIPS_DIR}")
    if args.dry_run:
        print("[VERIFY] DRY RUN - nothing will be saved")

    counts = {"real_fall": 0, "false_alarm": 0, "unsure": 0, "deleted": 0,
              "identified": 0, "reassigned": 0, "missing_clip": 0, "unreadable": 0, "errors": 0}
    rows = []

    for n, ev in enumerate(events, start=1):
        prefix = f"[{n}/{len(events)}] #{ev.id}"
        path = os.path.join(CLIPS_DIR, ev.clip_path)

        if not os.path.isfile(path):
            counts["missing_clip"] += 1
            rows.append((ev.id, "clip file missing", "", ""))
            print(prefix, "clip file missing:", ev.clip_path)
            continue

        images = clip_images(path)
        if not images:
            counts["unreadable"] += 1
            rows.append((ev.id, "clip unreadable", "", ""))
            print(prefix, "could not read the clip:", ev.clip_path)
            continue

        try:
            raw = gv.ask(images, prompt_for(ev, teams))
        except Exception as e:
            counts["errors"] += 1
            rows.append((ev.id, "Gemini error", "", str(e)[:60]))
            print(prefix, "Gemini failed:", e)
            time.sleep(args.delay)
            continue

        body = gv.to_backend(raw)
        counts[body["verdict"]] += 1
        jersey = f"#{body['jersey_number']} ({(body['jersey_confidence'] or 0):.0%})" if body["jersey_number"] is not None else "-"
        line = f"{body['verdict']} ({body['confidence']:.0%}) | jersey {jersey} | {body['team'] or '-'} | {body['description'] or ''}"
        print(prefix, line)

        action = "not saved (dry run)"
        if not args.dry_run:
            remove = (args.remove_false_alarms and body["verdict"] == "false_alarm"
                      and body["confidence"] >= gv.FALSE_ALARM_CONFIDENCE)
            try:
                answer = gv.send_result(ev.id, body, keep_false_alarm=not remove,
                                        min_jersey_confidence=args.min_jersey_confidence)
                action = gv.apply_answer(ev.id, body, answer,
                                         previous_player=ev.player.name if ev.player is not None else None)
                if action in counts:
                    counts[action] += 1
            except Exception as e:
                counts["errors"] += 1
                action = "save failed: " + str(e)[:60]
                print(prefix, "could not save the result:", e)

        rows.append((ev.id, f"{body['verdict']} {body['confidence']:.0%}", jersey, action))
        time.sleep(args.delay)

    db.close()

    print()
    print("=" * 72)
    print(f"{'Event':>6}  {'Gemini':<20} {'Jersey':<12} Result")
    print("-" * 72)
    for r in rows:
        print(f"{r[0]:>6}  {r[1]:<20} {r[2]:<12} {r[3]}")
    print("=" * 72)
    print("Real falls:", counts["real_fall"], "| False alarms:", counts["false_alarm"],
          "| Unsure:", counts["unsure"], "| Removed:", counts["deleted"])
    print("Players identified:", counts["identified"], "| Players corrected:", counts["reassigned"])
    print("Clip missing:", counts["missing_clip"], "| Unreadable:", counts["unreadable"], "| Errors:", counts["errors"])
    if counts["false_alarm"] and not args.remove_false_alarms and not args.dry_run:
        print("False alarms are marked in the dashboard, not deleted. "
              "Run again with --recheck --remove-false-alarms to delete the very sure ones.")


if __name__ == "__main__":
    main()