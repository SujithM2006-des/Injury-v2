"""
gemini_verifier.py - KEY 1 (GEMINI_API_KEY): removes FAKE and DUPLICATE fall detections.

Job of this check (the injury details are the job of gemini_injury.py, KEY 2):
  1. FAKE?       Is the boxed player really on the ground from a fall / tackle / collision,
                 or is it a false alarm (sliding tackle and straight up, keeper dive, celebration,
                 referee / coach, wrong person boxed ...)?          -> fake: event deleted
  2. DUPLICATE?  Was the SAME fall already saved a few seconds earlier (same player, same
                 incident, e.g. the player is still on the ground and was flagged again)?
                 Gemini compares this fall with the earlier falls of the last
                 DUPLICATE_WINDOW_SEC seconds of video.             -> duplicate: newer event deleted
  3. NO UNIDENTIFIED FALLS: Gemini reads the shirt number; when it cannot read it, it picks
     the most likely player of the roster (kit, position, build). An Unidentified fall gets
     that player straight away (the dashboard shows the name, WhatsApp gets the update).
     The detector's own jersey / face read still replaces a Gemini guess when it is surer.
Deleted events get a WhatsApp "please ignore" message (when their alert was sent).
gemini_injury.py waits for this check and skips events deleted here.

Interface used by multi_player_injury.py:
    start(), submit(ids, raw_frames, target_index, target_box, context),
    shutdown(), is_available(), player_changes, deleted_event_ids, stats
Also used by verify_clips.py (checks clips that are already saved):
    init(), ask(), to_backend(), send_result(), team_names()

What it does for each saved fall (runs in a background thread):
  - Sends the fall-moment frame (target player boxed), a zoomed crop and a few
    surrounding frames to Gemini.
  - Sends Gemini's answer to the backend (PATCH /events/{id}/gemini), which
    stores it and applies the rules:
      confident false alarm or duplicate -> event row (and its clip file) deleted
      confident jersey read that differs from / fills in our player -> event updated
Any error = event left untouched (fails safe).
Only the FIRST event id of a clip is judged (that is the boxed player).

Keys:  AIza... and AQ....  -> Gemini Developer API (AI Studio)
       Vertex AI is opt-in only: set GEMINI_USE_VERTEX=1 (needs billing enabled)
"""

import os
import json
import time
import queue
import threading
from collections import deque

import cv2
import requests
from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))

for _p in (
    os.path.join(_HERE, ".env"),
    os.path.join(_HERE, "..", ".env"),
    os.path.join(_HERE, "..", "backend", ".env"),
):
    if os.path.isfile(_p):
        load_dotenv(_p)

# ============================================
# SETTINGS
# ============================================

# Force one model without editing code:  $env:GEMINI_MODEL="gemini-3.5-flash-lite"
_ENV_MODEL = os.getenv("GEMINI_MODEL", "").strip()

FALSE_ALARM_CONFIDENCE = 0.85   # delete an event only if Gemini is at least this sure it is NOT a fall
DUPLICATE_CONFIDENCE = 0.85     # delete a fall as a duplicate only if Gemini is at least this sure
DUPLICATE_WINDOW_SEC = 20       # compare with earlier falls up to this many seconds before (video time)
MAX_DUPLICATE_CANDIDATES = 3    # earlier falls shown to Gemini at most
SEND_WHATSAPP_IGNORE = True     # WhatsApp "please ignore" after a fake / duplicate is deleted
FILL_UNIDENTIFIED = True        # every kept fall gets a player: jersey read, else Gemini's best guess
JERSEY_CONFIDENCE = 0.85        # replace/fill the player only if the jersey read is at least this sure
DECIDED_CONFIDENCE = 0.60       # below this the verdict is stored as "unsure"
MAX_SEQUENCE_FRAMES = 6         # surrounding frames sent besides the fall frame and the crop
JPEG_QUALITY = 85
MAX_RETRIES = 2
SHUTDOWN_TIMEOUT_SEC = 180

API_BASE = os.getenv("ATHLETEGUARD_API", "http://127.0.0.1:8000").rstrip("/")
API_TIMEOUT = 20

# Optional: set to a callable(text) to send a correction message (e.g. WhatsApp)
notify_hook = None

# ============================================
# STATE READ BY multi_player_injury.py
# ============================================

player_changes = {}        # event_id -> new player name
deleted_event_ids = set()  # event ids Gemini removed (fake or duplicate)
checked_event_ids = set()  # event ids this check has finished with (gemini_injury.py waits for these)
stats = {
    "checked": 0,
    "false_alarm_deleted": 0,
    "duplicate_deleted": 0,
    "reassigned": 0,
    "identified": 0,
    "errors": 0,
}

_client = None
_types = None
_models = []
_queue = queue.Queue()
_worker = None
_recent = deque(maxlen=12)  # falls kept in this run: {"event_id", "video_sec", "player", "images"}


def is_available():
    return _client is not None


# ============================================
# LIFECYCLE
# ============================================

def init():
    """Creates the Gemini client. Returns True when Gemini can be used."""
    global _client, _types, _models

    if _client is not None:
        return True

    key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

    if not key:
        print("[GEMINI] No GEMINI_API_KEY found - Gemini check disabled.")
        return False

    try:
        from google import genai
        from google.genai import types

        # Vertex AI is opt-in only. AI Studio keys (AIza... AND AQ....) use the normal client.
        use_vertex = os.getenv("GEMINI_USE_VERTEX", "").strip() == "1"

        if use_vertex:
            _client = genai.Client(vertexai=True, api_key=key)
            candidates = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.5-flash"]
            mode = "Vertex AI express"
        else:
            _client = genai.Client(api_key=key)
            candidates = [
                "gemini-3.5-flash-lite",
                "gemini-3.8-flash",
                "gemini-3.5-flash",
                "gemini-3.1-flash-lite",
                "gemini-flash-latest",
            ]
            mode = "Gemini API"

        _types = types
        _models = [_ENV_MODEL] if _ENV_MODEL else candidates

    except Exception as e:
        print("[GEMINI] Could not start (pip install google-genai):", e)
        _client = None
        return False

    print("[GEMINI] Fake / duplicate check ON |", mode, "| model:", _models[0])
    return True


def start():
    global _worker

    if not init():
        return

    _worker = threading.Thread(target=_worker_loop, daemon=True)
    _worker.start()


def submit(ids, raw_frames, target_index, target_box, context):
    if _client is None:
        return

    ids = [i for i in (ids or []) if i is not None]

    if not ids or not raw_frames:
        return

    _queue.put((ids, list(raw_frames), int(target_index), target_box, dict(context or {})))


def shutdown():
    if _worker is None:
        return

    pending = _queue.qsize()

    if pending:
        print("[GEMINI] Waiting for", pending, "pending check(s) to finish...")

    _queue.put(None)
    _worker.join(timeout=SHUTDOWN_TIMEOUT_SEC)

    if _worker.is_alive():
        print("[GEMINI] Timed out waiting for remaining checks - leaving them unchecked.")


def _worker_loop():
    while True:
        job = _queue.get()

        if job is None:
            break

        try:
            _process(job)
        except Exception as e:
            stats["errors"] += 1
            print("[GEMINI] Check failed (event kept as is):", e)
        finally:
            for event_id in job[0]:
                checked_event_ids.add(event_id)


# ============================================
# IMAGES
# ============================================

def _jpeg(img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes() if ok else None


def _build_images(frames, target_index, box):
    """Returns [(label, jpeg_bytes), ...]"""

    n = len(frames)
    ti = max(0, min(target_index, n - 1))
    out = []

    h, w = frames[ti].shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, x2 = max(0, min(x1, w - 1)), max(0, min(x2, w - 1))
    y1, y2 = max(0, min(y1, h - 1)), max(0, min(y2, h - 1))

    # 1) fall-moment frame with the flagged player boxed
    annotated = frames[ti].copy()
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 3)
    cv2.putText(annotated, "TARGET", (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    data = _jpeg(annotated)
    if data:
        out.append(("Image 1 - fall-moment frame, flagged player in the green TARGET box:", data))

    # 2) zoomed crop of that player (raw, no overlay) for jersey reading
    pad_x = int((x2 - x1) * 0.25)
    pad_y = int((y2 - y1) * 0.25)
    cx1, cy1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    cx2, cy2 = min(w, x2 + pad_x), min(h, y2 + pad_y)

    if cx2 - cx1 > 8 and cy2 - cy1 > 8:
        crop = frames[ti][cy1:cy2, cx1:cx2]
        scale = min(4.0, max(1.0, 640.0 / crop.shape[1]))
        if scale > 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        data = _jpeg(crop)
        if data:
            out.append(("Image 2 - zoomed crop of the flagged player:", data))

    # 3) a few chronological frames around the event (no boxes)
    if n <= MAX_SEQUENCE_FRAMES:
        picks = list(range(n))
    else:
        step = (n - 1) / float(MAX_SEQUENCE_FRAMES - 1)
        picks = sorted({int(round(i * step)) for i in range(MAX_SEQUENCE_FRAMES)} | {ti})

    for k, idx in enumerate(picks, start=1):
        data = _jpeg(frames[idx])
        if data:
            when = "FALL MOMENT" if idx == ti else ("before" if idx < ti else "after")
            out.append((f"Sequence frame {k}/{len(picks)} ({when}):", data))

    return out


# ============================================
# GEMINI CALL
# ============================================

def _prompt(context, team_names, candidates=None, teams_roster=None):
    teams = ", ".join(team_names) if team_names else "unknown"
    roster_text = _roster_text(teams_roster or {})
    ctx = json.dumps(context, default=str)[:600] if context else "none"
    candidates = candidates or []

    if candidates:
        listed = "; ".join(f"#{c['event_id']} at {c['video_time']} ({c['player'] or 'Unidentified'})" for c in candidates)
        duplicate_step = f"""8. duplicate_of: the images labelled "EARLIER FALL #..." show falls that were already saved a few seconds
   before this one ({listed}). If the boxed player here is the SAME player in the SAME incident as one of
   them (same fall, e.g. still lying on the ground or getting up, flagged again), give that event number.
   A different player, or the same player in a NEW separate fall, is NOT a duplicate: use null.
9. duplicate_confidence: 0.0-1.0 for duplicate_of (0 if null).
10. duplicate_reason: one short sentence for the duplicate decision."""
    else:
        duplicate_step = """8. duplicate_of: null (no earlier fall to compare with).
9. duplicate_confidence: 0.
10. duplicate_reason: empty."""

    return f"""You are verifying an automatic fall detector on football (soccer) broadcast footage.
The detector flagged the player inside the green TARGET box in image 1 as having fallen / being on the ground.
Image 2 is a zoomed crop of that player. The remaining images are chronological frames around the event (no boxes).

Decide:
1. real_fall: true if the boxed player is genuinely on the ground from a fall, tackle, collision or injury.
   false for a FALSE ALARM: player upright/running/jumping, bending or tying boots, celebrating, a routine
   intentional slide or dive where the player immediately gets up, a referee / coach / ball boy / spectator,
   the wrong person boxed, or nothing visibly wrong. If the images are too unclear to judge, use low confidence.
2. confidence: 0.0-1.0 for that judgment (below 0.6 when unclear).
3. jersey_number: shirt number of the boxed player ONLY if clearly readable in the images, else null. Never guess.
4. jersey_confidence: 0.0-1.0 for the number read (0 if null).
5. team: the boxed player's team from [{teams}] judged from kit colours, else null.
6. description: one short sentence describing what happens to the player (e.g. "tackled from behind, lands on the left knee and stays down").
7. reason: one short sentence explaining your real_fall decision.
{duplicate_step}
11. player: the boxed player's NAME, exactly as written in the squad list below. Use the shirt number when
    you can read it. When you cannot, still pick the MOST LIKELY player of that team from the kit, the
    position on the pitch (goalkeeper, defender, forward), hair, skin tone, build and the captain's armband.
    Always give a name from the list - never null - unless the boxed person is clearly not a player.
12. player_confidence: 0.0-1.0 for that name (low, e.g. 0.3, when it is a best guess).

Squad list:
{roster_text}

Detector context (may be partial): {ctx}

Reply with JSON only:
{{"real_fall": true, "confidence": 0.0, "jersey_number": null, "jersey_confidence": 0.0, "team": null, "description": "", "reason": "", "duplicate_of": null, "duplicate_confidence": 0.0, "duplicate_reason": "", "player": null, "player_confidence": 0.0}}"""


def _make_config():
    types = _types

    kwargs = dict(
        response_mime_type="application/json",
        temperature=0.0,
    )

    # Silences the harmless "automatic function calling" warning (skipped if this
    # version of google-genai doesn't have the option).
    afc_cls = getattr(types, "AutomaticFunctionCallingConfig", None)
    if afc_cls is not None:
        try:
            kwargs["automatic_function_calling"] = afc_cls(disable=True)
        except Exception:
            pass

    return types.GenerateContentConfig(**kwargs)


def _ask(images, context, team_names, prompt=None, candidates=None, teams_roster=None):
    global _models

    types = _types

    contents = []
    for label, data in images:
        contents.append(label)
        contents.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
    for c in candidates or []:
        for label, data in c["images"]:
            contents.append(f"EARLIER FALL #{c['event_id']} at {c['video_time']} - {label}")
            contents.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
    contents.append(prompt or _prompt(context, team_names, candidates, teams_roster))

    config = _make_config()

    last_error = None

    for attempt in range(MAX_RETRIES + 1):

        for model in list(_models):
            try:
                resp = _client.models.generate_content(model=model, contents=contents, config=config)
                text = (resp.text or "").strip()

                if text.startswith("```"):
                    text = text.strip("`")
                    if text.lower().startswith("json"):
                        text = text[4:]

                data = json.loads(text)

                if isinstance(data, list) and data:
                    data = data[0]

                # remember the model that worked
                if _models and _models[0] != model:
                    _models = [model] + [m for m in _models if m != model]

                return data

            except Exception as e:
                last_error = e
                msg = str(e)

                if any(s in msg for s in ("404", "NOT_FOUND", "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED")):
                    continue   # model missing, overloaded or rate-limited - try the next one

                break          # other errors: wait and retry

        time.sleep(2 * (attempt + 1))

    raise RuntimeError(f"Gemini request failed: {last_error}")


def _as_bool(v, default=True):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "no", "0")
    return default


def _as_float(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


# ============================================
# APPLY THE VERDICT (through the backend, so it is stored and shown in the dashboard)
# ============================================

def ask(images, prompt):
    """Public wrapper for verify_clips.py."""
    return _ask(images, None, None, prompt=prompt)


def to_backend(raw):
    """Gemini's JSON -> body for PATCH /events/{id}/gemini."""

    real_fall = _as_bool(raw.get("real_fall"), True)
    confidence = _as_float(raw.get("confidence"))

    if confidence < DECIDED_CONFIDENCE:
        verdict = "unsure"
    else:
        verdict = "real_fall" if real_fall else "false_alarm"

    try:
        jersey = int(raw.get("jersey_number")) if raw.get("jersey_number") is not None else None
    except (TypeError, ValueError):
        jersey = None

    team = str(raw.get("team") or "").strip() or None

    return {
        "verdict": verdict,
        "confidence": confidence,
        "reason": str(raw.get("reason") or "")[:300] or None,
        "description": str(raw.get("description") or "")[:300] or None,
        "team": team,
        "jersey_number": jersey,
        "jersey_confidence": _as_float(raw.get("jersey_confidence")) if jersey is not None else None,
    }


def send_result(event_id, body, keep_false_alarm=False, min_jersey_confidence=JERSEY_CONFIDENCE):
    """Stores the verdict through the backend. Returns the backend's answer ({"action": ...})."""

    params = {"min_jersey_confidence": min_jersey_confidence}
    if keep_false_alarm:
        params["keep_false_alarm"] = "true"

    r = requests.patch(API_BASE + "/events/" + str(event_id) + "/gemini", json=body, params=params, timeout=API_TIMEOUT)

    if r.status_code == 404:
        return {"action": "missing"}

    r.raise_for_status()
    return r.json()


def roster():
    """{"Portugal": [(5, "Fernando Meira", player_id), ...], ...} from the database."""
    try:
        from database import SessionLocal
        from models import Team, Player
        db = SessionLocal()
        try:
            out = {}
            for p, t in db.query(Player, Team).join(Team, Team.id == Player.team_id).order_by(Team.id, Player.jersey_number):
                out.setdefault(t.name, []).append((p.jersey_number, p.name, p.id))
            return out
        finally:
            db.close()
    except Exception as e:
        print("[GEMINI] Could not read the roster:", e)
        return {}


def _roster_text(teams_roster):
    lines = []
    for team, players in teams_roster.items():
        lines.append(team + ": " + ", ".join(f"#{n} {name}" for n, name, _ in players))
    return "\n".join(lines) or "unknown"


def team_names():
    try:
        from database import SessionLocal
        from models import Team
        db = SessionLocal()
        try:
            return [t.name for t in db.query(Team).order_by(Team.id).all()]
        finally:
            db.close()
    except Exception as e:
        print("[GEMINI] Could not read team names:", e)
        return []


def _notify(text):
    print("[GEMINI]", text)

    if notify_hook is not None:
        try:
            notify_hook(text)
        except Exception as e:
            print("[GEMINI] notify_hook failed:", e)


def apply_answer(event_id, body, answer, previous_player=None):
    """Updates the counters and prints/notifies what the backend did."""

    action = answer.get("action")
    event = answer.get("event") or {}
    conf = body.get("confidence") or 0.0

    if action == "deleted":
        deleted_event_ids.add(event_id)
        stats["false_alarm_deleted"] += 1
        _notify(
            f"Correction: event #{event_id} ({previous_player or 'Unidentified'}) was a false alarm and was removed "
            f"(confidence {conf:.2f}). {body.get('reason') or ''}"
        )

    elif action in ("identified", "reassigned"):
        name = event.get("player_name")
        player_changes[event_id] = name
        if action == "identified":
            stats["identified"] += 1
            _notify(f"Event #{event_id} identified by Gemini as {name} (#{body.get('jersey_number')}).")
        else:
            stats["reassigned"] += 1
            _notify(
                f"Correction: event #{event_id} was {previous_player}, now {name} (#{body.get('jersey_number')}) "
                f"per Gemini (confidence {(body.get('jersey_confidence') or 0):.2f})."
            )

    return action


# ============================================
# DUPLICATES AND "PLEASE IGNORE" MESSAGES
# ============================================

def _video_sec(text):
    """'0:38:55' -> 2335.0 (None if missing)."""
    try:
        h, m, s = [int(x) for x in str(text).split(":")]
        return float(h * 3600 + m * 60 + s)
    except (TypeError, ValueError):
        return None


def _duplicate_candidates(video_sec):
    """Falls kept earlier in this run, at most DUPLICATE_WINDOW_SEC before this one."""
    if video_sec is None:
        return []
    out = [c for c in _recent
           if c["event_id"] not in deleted_event_ids
           and 0 <= video_sec - c["video_sec"] <= DUPLICATE_WINDOW_SEC]
    return out[-MAX_DUPLICATE_CANDIDATES:]


def _duplicate_of(raw, candidates):
    """Gemini's duplicate answer -> (earlier event id, confidence, reason) or (None, 0, None)."""
    try:
        dup = int(raw.get("duplicate_of")) if raw.get("duplicate_of") not in (None, "", "null") else None
    except (TypeError, ValueError):
        dup = None
    if dup is None or dup not in {c["event_id"] for c in candidates}:
        return None, 0.0, None
    return dup, _as_float(raw.get("duplicate_confidence")), str(raw.get("duplicate_reason") or "")[:200] or None


def _alert_was_sent(event_id):
    """The first WhatsApp alert is skipped for duplicates of an earlier run - no follow-up then either."""
    try:
        import alert_system
        return event_id not in alert_system._duplicate_event_ids
    except Exception:
        return True


def _send_ignore(event_id, context, why):
    if not SEND_WHATSAPP_IGNORE or not _alert_was_sent(event_id):
        return
    who = (context or {}).get("player") or "Unidentified player"
    when = (" at " + context["video_time"]) if (context or {}).get("video_time") else ""
    try:
        import whatsapp_notifier
        whatsapp_notifier.send_message(
            "\u2705 AthleteGuard update\nEvent #" + str(event_id) + " - " + who + when
            + "\n" + why + " Please ignore the earlier alert."
        )
    except Exception as e:
        print("[GEMINI] WhatsApp 'please ignore' not sent:", e)


def _pick_player(raw, body, teams_roster):
    """Gemini's answer -> (player_id, name, jersey, detail, confidence) or None."""
    every = [(team, n, name, pid) for team, players in teams_roster.items() for n, name, pid in players]
    if not every:
        return None
    team = (body.get("team") or "").strip().lower()
    jersey = body.get("jersey_number")

    # 1) readable shirt number (+ team when known)
    if jersey is not None:
        hits = [x for x in every if x[1] == jersey and (not team or x[0].lower() == team)]
        if len(hits) == 1:
            t, n, name, pid = hits[0]
            return pid, name, n, f"Gemini read #{n} ({t})", max(0.5, body.get("jersey_confidence") or 0.5)

    # 2) Gemini's named pick from the squad list
    guess = str(raw.get("player") or "").strip().lower()
    if guess:
        hits = [x for x in every if x[2].lower() == guess] or [x for x in every if guess in x[2].lower() or x[2].lower() in guess]
        if hits:
            t, n, name, pid = hits[0]
            conf = _as_float(raw.get("player_confidence")) or 0.3
            return pid, name, n, f"Gemini best guess from the clip ({t}, kit and position)", min(conf, 0.84)
    return None


def _fill_unidentified(event_id, raw, body, answer, teams_roster, context):
    """The fall is kept but still Unidentified -> give it Gemini's player right away."""
    if not FILL_UNIDENTIFIED:
        return
    event = answer.get("event") or {}
    if event.get("identified"):
        return
    pick = _pick_player(raw, body, teams_roster)
    if pick is None:
        print(f"[GEMINI] #{event_id}: no player could be picked - stays Unidentified")
        return
    pid, name, jersey, detail, conf = pick
    try:
        import alert_system   # PATCH /events/{id}/ai-update + WhatsApp "the earlier Unidentified fall was ..."
        ok = alert_system.update_event_player(
            event_id, pid, name, jersey_number=jersey, event_type=event.get("event_type") or "FALL",
            match_name=event.get("match_name"), identified_by="gemini", id_detail=detail, id_confidence=conf,
        )
    except Exception as e:
        print(f"[GEMINI] #{event_id}: could not store the player:", e)
        return
    if ok:
        player_changes[event_id] = name
        stats["identified"] += 1
        _notify(f"Event #{event_id} identified by Gemini as {name} (#{jersey}) - {detail}, {conf:.0%}.")


def _process(job):
    ids, frames, target_index, box, context = job
    event_id = ids[0]   # the clip's target box belongs to the first event

    images = _build_images(frames, target_index, box)

    if not images:
        return

    video_sec = _video_sec((context or {}).get("video_time"))
    candidates = _duplicate_candidates(video_sec)

    teams_roster = roster()
    raw = _ask(images, context, list(teams_roster) or team_names(), candidates=candidates, teams_roster=teams_roster)
    stats["checked"] += 1

    body = to_backend(raw)
    dup, dup_conf, dup_reason = _duplicate_of(raw, candidates)

    print(f"[GEMINI] #{event_id}: {body['verdict']} ({body['confidence']:.2f}) | "
          f"jersey={body['jersey_number']} ({(body['jersey_confidence'] or 0):.2f}) | "
          f"team={body['team']} | {body['reason']}"
          + (f" | duplicate of #{dup} ({dup_conf:.2f})" if dup is not None else ""))

    previous = (context or {}).get("player")

    # 1) FAKE: removed only when Gemini is at least FALSE_ALARM_CONFIDENCE sure
    fake = body["verdict"] == "false_alarm" and body["confidence"] >= FALSE_ALARM_CONFIDENCE

    # 2) DUPLICATE of a fall saved a few seconds earlier: the newer event is removed
    if not fake and dup is not None and dup_conf >= DUPLICATE_CONFIDENCE:
        dup_body = dict(body, verdict="false_alarm", confidence=dup_conf,
                        reason=f"Duplicate of event #{dup}. {dup_reason or ''}".strip())
        answer = send_result(event_id, dup_body, min_jersey_confidence=JERSEY_CONFIDENCE)
        if answer.get("action") == "deleted":
            deleted_event_ids.add(event_id)
            stats["duplicate_deleted"] += 1
            _notify(f"Event #{event_id} ({previous or 'Unidentified'}) removed - duplicate of event #{dup} "
                    f"(confidence {dup_conf:.2f}). {dup_reason or ''}")
            _send_ignore(event_id, context, f"Same fall as event #{dup} (detected twice).")
            return
        # not deleted (e.g. a staff member already identified it): keep it as a normal fall below

    keep = not fake
    answer = send_result(event_id, body, keep_false_alarm=keep, min_jersey_confidence=JERSEY_CONFIDENCE)
    action = apply_answer(event_id, body, answer, previous_player=previous)

    if action == "deleted":
        _send_ignore(event_id, context, "Not a real fall (" + (body.get("reason") or "false alarm") + ").")
        return

    # kept and still Unidentified -> Gemini's player straight away (no waiting for the detector)
    if action not in ("identified", "reassigned", "missing"):
        _fill_unidentified(event_id, raw, body, answer, teams_roster, context)

    # kept -> later falls are compared with this one
    if video_sec is not None and action != "missing":
        _recent.append({
            "event_id": event_id,
            "video_sec": video_sec,
            "video_time": context.get("video_time"),
            "player": player_changes.get(event_id) or previous,
            "images": images[:2],   # boxed fall frame + zoomed crop
        })