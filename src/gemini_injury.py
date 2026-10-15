"""
gemini_injury.py - KEY 2 (GEMINI_INJURY_API_KEY): possible injuries of the REAL falls.

Key:  GEMINI_INJURY_API_KEY in .env   (falls back to GEMINI_API_KEY if not set)
On only when .env has GEMINI_INJURY_CHECK=1.

Fake and duplicate falls are removed by KEY 1 (gemini_verifier.py). This check waits for
that decision, skips the removed events, and NEVER deletes anything itself.

For each remaining fall (background thread, never slows detection):
  - Gemini watches the clip: which body part took the impact and how, and picks the
    possible injuries ONLY from injury_catalog.py.
  - Risk, the recommended safety measure (first step) and the rest time always come from
    the catalog, never invented by Gemini.
  - Stored through the backend (PATCH /events/{id}/ai-injury -> output/ai_injury.json),
    shown on the dashboard, and sent as a WhatsApp follow-up.

After this check, every remaining fall is handed to KEY 3 (gemini_treatment.py, own key
GEMINI_TREATMENT_API_KEY) for the detailed medical recommendation (tests, treatment).

Any error = event left exactly as it is (fails safe).

Interface used by multi_player_injury.py:
    start(), submit(ids, raw_frames, target_index, target_box, context), shutdown(),
    is_available(), deleted_event_ids, results, stats
"""

import os
import json
import time
import queue
import threading

import cv2
import requests
from dotenv import load_dotenv

import injury_catalog

try:
    import gemini_treatment          # KEY 3 - optional; missing file = no medical recommendation
except Exception as _e:
    gemini_treatment = None
    print("[TREATMENT-AI] gemini_treatment.py not loaded - medical recommendation off:", _e)

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

# Force one model without editing code:  $env:GEMINI_INJURY_MODEL="gemini-3.5-flash"
_ENV_MODEL = os.getenv("GEMINI_INJURY_MODEL", "").strip() or os.getenv("GEMINI_MODEL", "").strip()

WAIT_FOR_FAKE_CHECK_SEC = 300        # how long to wait for KEY 1's fake / duplicate decision
MAX_INJURIES = 3                      # possible injuries kept per event
MAX_SEQUENCE_FRAMES = 10              # chronological frames sent besides the boxed frame and the crop
JPEG_QUALITY = 85
MAX_RETRIES = 2
SHUTDOWN_TIMEOUT_SEC = 240

SEND_WHATSAPP_FOLLOW_UP = True        # send the possible injuries message after the first alert

API_BASE = os.getenv("ATHLETEGUARD_API", "http://127.0.0.1:8000").rstrip("/")
API_TIMEOUT = 20

DISCLAIMER = "AI estimate from the clip, not a medical diagnosis. Return to play is a medical decision."

# ============================================
# STATE READ BY multi_player_injury.py
# ============================================

deleted_event_ids = set()   # always empty: this check never deletes (kept for multi_player_injury.py)
results = {}                # event_id -> stored injury result
stats = {"checked": 0, "not_injury_deleted": 0, "skipped_removed": 0, "injuries_found": 0, "errors": 0}

_client = None
_types = None
_models = []
_key_name = None
_queue = queue.Queue()
_worker = None


def is_available():
    return _client is not None


# ============================================
# LIFECYCLE
# ============================================

def init():
    """Creates the Gemini client for the injury check. Returns True when it can be used."""
    global _client, _types, _models, _key_name

    if _client is not None:
        return True

    key = os.getenv("GEMINI_INJURY_API_KEY", "").strip()
    _key_name = "GEMINI_INJURY_API_KEY"

    if not key:
        key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        _key_name = "GEMINI_API_KEY (no GEMINI_INJURY_API_KEY set)"

    if not key:
        print("[INJURY-AI] No GEMINI_INJURY_API_KEY found - injury check disabled.")
        return False

    try:
        from google import genai
        from google.genai import types

        if os.getenv("GEMINI_USE_VERTEX", "").strip() == "1":
            _client = genai.Client(vertexai=True, api_key=key)
        else:
            _client = genai.Client(api_key=key)

        _types = types
        _models = [_ENV_MODEL] if _ENV_MODEL else [
            "gemini-3.5-flash",
            "gemini-3.8-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-flash-latest",
        ]

    except Exception as e:
        print("[INJURY-AI] Could not start (pip install google-genai):", e)
        _client = None
        return False

    print("[INJURY-AI] Possible-injury check ON | key:", _key_name, "| model:", _models[0], "| never deletes")
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

    if not ids or not raw_frames or target_box is None:
        return

    _queue.put((ids, list(raw_frames), int(target_index), target_box, dict(context or {})))


def shutdown():
    if _worker is None:
        return

    pending = _queue.qsize()

    if pending:
        print("[INJURY-AI] Waiting for", pending, "pending injury check(s) to finish...")

    _queue.put(None)
    _worker.join(timeout=SHUTDOWN_TIMEOUT_SEC)

    if _worker.is_alive():
        print("[INJURY-AI] Timed out - remaining events keep the detector's own note.")


def _worker_loop():
    while True:
        job = _queue.get()

        if job is None:
            break

        try:
            _process(job)
        except Exception as e:
            stats["errors"] += 1
            print("[INJURY-AI] Check failed (event kept as is):", e)


# ============================================
# IMAGES
# ============================================

def _jpeg(img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes() if ok else None


def _build_images(frames, target_index, box):
    """[(label, jpeg_bytes), ...]: boxed fall frame, zoomed crop, then the clip in order."""

    n = len(frames)
    ti = max(0, min(target_index, n - 1))
    out = []

    h, w = frames[ti].shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, x2 = max(0, min(x1, w - 1)), max(0, min(x2, w - 1))
    y1, y2 = max(0, min(y1, h - 1)), max(0, min(y2, h - 1))

    annotated = frames[ti].copy()
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 3)
    cv2.putText(annotated, "TARGET", (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    data = _jpeg(annotated)
    if data:
        out.append(("Image A - the moment the detector flagged, player in the green TARGET box:", data))

    pad_x = int((x2 - x1) * 0.35)
    pad_y = int((y2 - y1) * 0.35)
    cx1, cy1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    cx2, cy2 = min(w, x2 + pad_x), min(h, y2 + pad_y)

    if cx2 - cx1 > 8 and cy2 - cy1 > 8:
        crop = frames[ti][cy1:cy2, cx1:cx2]
        scale = min(4.0, max(1.0, 640.0 / crop.shape[1]))
        if scale > 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        data = _jpeg(crop)
        if data:
            out.append(("Image B - zoomed crop of that player (body position, which body part hit the ground):", data))

    if n <= MAX_SEQUENCE_FRAMES:
        picks = list(range(n))
    else:
        step = (n - 1) / float(MAX_SEQUENCE_FRAMES - 1)
        picks = sorted({int(round(i * step)) for i in range(MAX_SEQUENCE_FRAMES)} | {ti})

    for k, idx in enumerate(picks, start=1):
        data = _jpeg(frames[idx])
        if data:
            when = "FLAGGED MOMENT" if idx == ti else ("before" if idx < ti else "after")
            out.append((f"Clip frame {k}/{len(picks)} ({when}):", data))

    return out


# ============================================
# GEMINI CALL
# ============================================

def _prompt(context):
    region = (context or {}).get("region") or "unknown"
    hints = injury_catalog.hint_areas(region)

    return f"""You are a football (soccer) sports-medicine assistant reviewing a short clip from match footage.
An automatic detector flagged the player in the green TARGET box (image A) as having fallen.
Image B is a zoomed crop of that player. The "Clip frame" images are the clip in time order.

This fall has already been checked and confirmed as a REAL fall (not a fake, not a duplicate).

STEP 1 - Which body part took the impact, and how? Look at how the player lands and what happens
after: which part hits the ground or the opponent first, a knee or ankle twisting, an arm planted,
head or neck impact, the player clutching or holding a body part, limping, not putting weight on a leg.
Set injury_event = true if the player could be hurt, false only if he clearly gets up unhurt at once.

STEP 2 - Pick up to {MAX_INJURIES} possible injuries for that body part, most likely first.
Use ONLY names from this list, written exactly as shown:
{injury_catalog.as_prompt_text()}

The detector's movement analysis pointed at: {region}  (catalog areas to consider first: {", ".join(hints) or "any"}).
Trust what you actually see in the clip over this hint.

Reply with JSON only:
{{"injury_event": true,
  "confidence": 0.0,
  "action": "short name of what happened, e.g. sliding tackle / heavy tackle from behind / awkward landing",
  "description": "one sentence: what happens to the player and which body part takes the impact",
  "side": "left / right / unknown",
  "possible_injuries": [{{"injury": "exact name from the list", "body_area": "area from the list", "likelihood": 0.0}}],
  "reason": "one short sentence: which body part and why"}}
confidence is 0.0-1.0 for the injury_event decision (below 0.6 when the clip is unclear).
possible_injuries is [] only when the player clearly gets up unhurt at once."""


def _make_config():
    kwargs = dict(response_mime_type="application/json", temperature=0.0)

    afc_cls = getattr(_types, "AutomaticFunctionCallingConfig", None)
    if afc_cls is not None:
        try:
            kwargs["automatic_function_calling"] = afc_cls(disable=True)
        except Exception:
            pass

    return _types.GenerateContentConfig(**kwargs)


def _ask(images, context):
    global _models

    contents = []
    for label, data in images:
        contents.append(label)
        contents.append(_types.Part.from_bytes(data=data, mime_type="image/jpeg"))
    contents.append(_prompt(context))

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

                if _models and _models[0] != model:
                    _models = [model] + [m for m in _models if m != model]

                return data

            except Exception as e:
                last_error = e
                msg = str(e)

                if any(s in msg for s in ("404", "NOT_FOUND", "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED")):
                    continue

                break

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
# TURN GEMINI'S ANSWER INTO THE STORED RESULT
# ============================================

def interpret(raw):
    """Gemini JSON -> {"injury_event", "confidence", ..., "injuries": [catalog rows]}."""

    injuries = []
    seen = set()

    for item in raw.get("possible_injuries") or []:
        if not isinstance(item, dict):
            item = {"injury": item}
        row = injury_catalog.find(item.get("injury"), item.get("body_area"))
        if row is None or row["injury"] in seen:
            continue            # not in the catalog -> ignored, Gemini may not invent injuries
        seen.add(row["injury"])
        row["likelihood"] = _as_float(item.get("likelihood"))
        injuries.append(row)
        if len(injuries) >= MAX_INJURIES:
            break

    side = str(raw.get("side") or "").strip().lower()

    return {
        "injury_event": _as_bool(raw.get("injury_event"), True),
        "confidence": _as_float(raw.get("confidence")),
        "action": str(raw.get("action") or "").strip()[:120] or None,
        "description": str(raw.get("description") or "").strip()[:300] or None,
        "reason": str(raw.get("reason") or "").strip()[:300] or None,
        "side": side if side in ("left", "right") else None,
        "injuries": injuries,
        "rest": injuries[0]["rest"] if injuries else None,
        "risk": injury_catalog.highest_risk([i["risk"] for i in injuries]),
    }


def _patch(path, body, params=None):
    r = requests.patch(API_BASE + path, json=body, params=params or {}, timeout=API_TIMEOUT)
    if r.status_code == 404:
        return {"action": "missing"}
    r.raise_for_status()
    return r.json()


def _alert_was_sent(event_id):
    """The first WhatsApp alert is skipped for duplicates of an earlier run - no follow-up then either."""
    try:
        import alert_system
        return event_id not in alert_system._duplicate_event_ids
    except Exception:
        return True


def _send_whatsapp(text):
    if not SEND_WHATSAPP_FOLLOW_UP:
        return
    try:
        import whatsapp_notifier
        whatsapp_notifier.send_message(text)
    except Exception as e:
        print("[INJURY-AI] WhatsApp follow-up not sent:", e)


def _player_text(context):
    return (context or {}).get("player") or "Unidentified player"


def follow_up_message(event_id, context, result):
    lines = [
        "\U0001FA7A AthleteGuard injury review",
        "Event #" + str(event_id) + " - " + _player_text(context),
    ]
    if (context or {}).get("video_time"):
        lines.append("Video time: " + context["video_time"])
    if result.get("description"):
        lines.append("What happened: " + result["description"])
    lines.append("")
    lines.append("Possible injuries:")
    for i in result["injuries"]:
        lines.append("- " + i["injury"] + " (" + i["body_area"] + ", " + i["risk"] + " risk) - rest " + i["rest"])
        lines.append("  First step: " + i["safety_measure"])
    lines.append("")
    lines.append("Expected rest: " + (result.get("rest") or "-") + " (most likely injury)")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def _wait_for_fake_check(event_id):
    """Waits for KEY 1 (gemini_verifier.py). False = the event was removed as fake / duplicate."""
    try:
        import gemini_verifier
    except Exception:
        return True
    if not gemini_verifier.is_available():
        return True     # KEY 1 is off: nothing to wait for
    waited = 0.0
    while event_id not in gemini_verifier.checked_event_ids and waited < WAIT_FOR_FAKE_CHECK_SEC:
        time.sleep(1.0)
        waited += 1.0
    return event_id not in gemini_verifier.deleted_event_ids


def _process(job):
    ids, frames, target_index, box, context = job
    event_id = ids[0]   # the boxed player belongs to the first event of the clip

    # KEY 1 decides about fake / duplicate falls first - removed ones are not checked here
    if not _wait_for_fake_check(event_id):
        stats["skipped_removed"] += 1
        print(f"[INJURY-AI] #{event_id} skipped - removed as fake / duplicate.")
        return

    hints = []
    try:
        _injury_check(event_id, frames, target_index, box, context, hints)
    finally:
        # KEY 3: detailed medical recommendation (tests, treatment) - also when this check failed
        if gemini_treatment is not None:
            gemini_treatment.submit(ids, frames, target_index, box, context, hints)


def _injury_check(event_id, frames, target_index, box, context, hints):
    images = _build_images(frames, target_index, box)
    if not images:
        return

    result = interpret(_ask(images, context))
    hints.extend(i["injury"] for i in result["injuries"])
    stats["checked"] += 1

    print(f"[INJURY-AI] #{event_id}: injury={result['injury_event']} ({result['confidence']:.2f}) | "
          f"{result['action']} | " + (", ".join(i["injury"] for i in result["injuries"]) or "no injuries")
          + (f" | rest {result['rest']}" if result["rest"] else ""))

    # this check never deletes: no possible injuries -> the event keeps the detector's own note
    if not result["injuries"]:
        return

    body = {
        "injury_event": result["injury_event"],
        "confidence": result["confidence"],
        "action": result["action"],
        "description": result["description"],
        "side": result["side"],
        "injuries": result["injuries"],
        "rest": result["rest"],
        "risk": result["risk"],
        "model": _models[0] if _models else None,
    }

    answer = _patch("/events/" + str(event_id) + "/ai-injury", body)

    if answer.get("action") == "missing":
        return

    results[event_id] = body
    stats["injuries_found"] += 1

    if _alert_was_sent(event_id):
        _send_whatsapp(follow_up_message(event_id, context, result))