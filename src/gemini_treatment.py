"""
gemini_treatment.py - KEY 3 (GEMINI_TREATMENT_API_KEY): detailed medical review of the REAL falls.

Key:  GEMINI_TREATMENT_API_KEY in .env   (own key - this check is OFF without it)

Runs after KEY 1 (fake / duplicate check, gemini_verifier.py) kept the fall and KEY 2
(possible injuries, gemini_injury.py) looked at it. KEY 2's possible injuries are passed
as a hint. This check NEVER deletes anything.

For each fall (background thread, never slows detection) Gemini studies the clip frame
by frame - the mechanism of injury (how the player lands, twisting, direct impact, what
happens after) - and returns:
  - the most likely injuries, each with why it is suspected
  - severity and urgency (emergency / same day / within 48 hours / routine)
  - immediate on-field safety measures
  - recommended tests (e.g. CT scan of the head, MRI of the knee, X-ray of the ankle)
  - treatment steps and the specialist to see
  - red flags to watch for, and return-to-play guidance
Stored through the backend (PATCH /events/{id}/ai-treatment -> output/ai_treatment.json),
shown on the event page as "Medical recommendation", and sent on WhatsApp.

AI decision support only - NOT a diagnosis. Every recommendation must be confirmed by a
qualified medical professional. Any error = event left exactly as it is (fails safe).

Used by gemini_injury.py:  submit(ids, raw_frames, target_index, target_box, context, hints)
"""

import os
import json
import time
import queue
import atexit
import threading

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

# Force one model without editing code:  $env:GEMINI_TREATMENT_MODEL="gemini-3.5-flash"
_ENV_MODEL = os.getenv("GEMINI_TREATMENT_MODEL", "").strip()

MAX_SEQUENCE_FRAMES = 16       # more frames than the other checks: the whole movement is studied
CROP_MOMENTS = 3               # zoomed crops of the player (before, at, after the fall)
JPEG_QUALITY = 88
MAX_RETRIES = 2
SHUTDOWN_TIMEOUT_SEC = 300

SEND_WHATSAPP = True           # send the medical recommendation on WhatsApp

API_BASE = os.getenv("ATHLETEGUARD_API", "http://127.0.0.1:8000").rstrip("/")
API_TIMEOUT = 20

SEVERITIES = ("Low", "Medium", "High", "Critical")
URGENCIES = ("Emergency", "Same day", "Within 48 hours", "Routine")

DISCLAIMER = ("AI decision support from the clip, NOT a diagnosis. "
              "A qualified medical professional must confirm every test and treatment.")

# ============================================
# STATE
# ============================================

results = {}     # event_id -> stored recommendation
stats = {"checked": 0, "stored": 0, "errors": 0}

_client = None
_types = None
_models = []
_queue = queue.Queue()
_worker = None
_started = False
_lock = threading.Lock()


def is_available():
    return _client is not None


# ============================================
# LIFECYCLE (starts by itself on the first fall)
# ============================================

def init():
    """Creates the Gemini client. Returns True when the treatment check can be used."""
    global _client, _types, _models

    if _client is not None:
        return True

    key = os.getenv("GEMINI_TREATMENT_API_KEY", "").strip()

    if not key:
        print("[TREATMENT-AI] No GEMINI_TREATMENT_API_KEY found - medical recommendation off.")
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
            "gemini-3.5-pro",
            "gemini-3.8-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest",
        ]

    except Exception as e:
        print("[TREATMENT-AI] Could not start (pip install google-genai):", e)
        _client = None
        return False

    print("[TREATMENT-AI] Medical recommendation ON | key: GEMINI_TREATMENT_API_KEY | model:", _models[0], "| never deletes")
    return True


def start():
    global _worker, _started

    with _lock:
        if _started:
            return
        _started = True
        if not init():
            return
        _worker = threading.Thread(target=_worker_loop, daemon=True)
        _worker.start()
        atexit.register(shutdown)


def submit(ids, raw_frames, target_index, target_box, context, hints=None):
    start()

    if _client is None:
        return

    ids = [i for i in (ids or []) if i is not None]

    if not ids or not raw_frames or target_box is None:
        return

    _queue.put((ids, list(raw_frames), int(target_index), target_box, dict(context or {}), list(hints or [])))


def shutdown():
    if _worker is None or not _worker.is_alive():
        return

    pending = _queue.qsize()

    if pending:
        print("[TREATMENT-AI] Waiting for", pending, "pending medical review(s) to finish...")

    _queue.put(None)
    _worker.join(timeout=SHUTDOWN_TIMEOUT_SEC)

    if _worker.is_alive():
        print("[TREATMENT-AI] Timed out - remaining events have no medical recommendation.")


def _worker_loop():
    while True:
        job = _queue.get()

        if job is None:
            break

        try:
            _process(job)
        except Exception as e:
            stats["errors"] += 1
            print("[TREATMENT-AI] Review failed (event kept as is):", e)


# ============================================
# IMAGES
# ============================================

def _jpeg(img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes() if ok else None


def _crop(frame, box, pad=0.4):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    px, py = int((x2 - x1) * pad), int((y2 - y1) * pad)
    cx1, cy1 = max(0, x1 - px), max(0, y1 - py)
    cx2, cy2 = min(w, x2 + px), min(h, y2 + py)
    if cx2 - cx1 <= 8 or cy2 - cy1 <= 8:
        return None
    crop = frame[cy1:cy2, cx1:cx2]
    scale = min(4.0, max(1.0, 720.0 / crop.shape[1]))
    if scale > 1.0:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return crop


def _build_images(frames, target_index, box):
    """[(label, jpeg_bytes), ...]: boxed fall frame, zoomed crops around it, then the clip in order."""

    n = len(frames)
    ti = max(0, min(target_index, n - 1))
    out = []

    h, w = frames[ti].shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, x2 = max(0, min(x1, w - 1)), max(0, min(x2, w - 1))
    y1, y2 = max(0, min(y1, h - 1)), max(0, min(y2, h - 1))

    annotated = frames[ti].copy()
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 3)
    cv2.putText(annotated, "PATIENT", (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    data = _jpeg(annotated)
    if data:
        out.append(("Image A - the fall moment, the injured player in the green PATIENT box:", data))

    # zoomed crops before / at / after the fall (same box area: the player is around there)
    step = max(1, n // 6)
    moments = sorted({max(0, ti - step), ti, min(n - 1, ti + step)})[:CROP_MOMENTS]
    for idx in moments:
        crop = _crop(frames[idx], (x1, y1, x2, y2))
        data = _jpeg(crop) if crop is not None else None
        if data:
            when = "AT the fall" if idx == ti else ("just BEFORE the fall" if idx < ti else "just AFTER the fall")
            out.append((f"Zoomed view of the player {when} (body position, which joint / body part takes the load):", data))

    if n <= MAX_SEQUENCE_FRAMES:
        picks = list(range(n))
    else:
        s = (n - 1) / float(MAX_SEQUENCE_FRAMES - 1)
        picks = sorted({int(round(i * s)) for i in range(MAX_SEQUENCE_FRAMES)} | {ti})

    for k, idx in enumerate(picks, start=1):
        data = _jpeg(frames[idx])
        if data:
            when = "FALL MOMENT" if idx == ti else ("before" if idx < ti else "after")
            out.append((f"Clip frame {k}/{len(picks)} ({when}):", data))

    return out


# ============================================
# GEMINI CALL
# ============================================

def _prompt(context, hints):
    region = (context or {}).get("region") or "unknown"
    player = (context or {}).get("player") or "the player"
    hint_text = ", ".join(hints) if hints else "none"

    return f"""You are an experienced football (soccer) team doctor and sports-medicine specialist.
Review this match clip of {player} going down. Image A shows the fall moment with the player in the
green PATIENT box, the zoomed views show the player just before, at and just after the fall, and the
"Clip frame" images are the whole clip in time order. The fall is already confirmed as REAL.

Analyse it like a pitch-side doctor:
1. MECHANISM: how exactly is the player injured? (e.g. foot planted and knee twisting inwards, landing on
   an outstretched arm, head-to-head contact, ankle rolling inwards, direct kick to the shin, whiplash).
   Which body part and side take the load or impact, and what does the player do afterwards (stays down,
   clutches a body part, cannot bear weight, lies still, gets up limping)?
2. LIKELY INJURIES: up to 3, most likely first, each with the visual reason you suspect it.
3. SEVERITY: Low / Medium / High / Critical.  URGENCY: Emergency / Same day / Within 48 hours / Routine.
4. ON-FIELD SAFETY MEASURES: what the medical staff should do right now on the pitch (e.g. do not move
   the neck, stop play, immobilise, ice, stretcher, check consciousness with a concussion test).
5. RECOMMENDED TESTS: imaging / examinations to order, each with why (e.g. "CT scan of the head - head
   impact with possible loss of consciousness", "MRI of the knee - suspected ACL tear", "X-ray of the
   wrist - fall on outstretched hand", "clinical concussion assessment (SCAT6)").
6. TREATMENT: the treatment steps (e.g. RICE for 48-72 h, brace, crutches, pain relief as prescribed,
   physiotherapy programme, surgery opinion if the test confirms a tear).
7. SPECIALIST: who should see the player (e.g. orthopaedic surgeon, neurologist, physiotherapist).
8. RED FLAGS: warning signs that mean emergency care (e.g. vomiting, worsening headache, numbness).
9. RETURN TO PLAY: realistic guidance (e.g. "not before medical clearance; typically 2-4 weeks").

The detector's movement analysis pointed at: {region}. Another check suggested: {hint_text}.
Trust what you actually see in the clip over these hints. If the clip is unclear, say so and stay
cautious (prefer the safer test). Never invent details you cannot see.

Reply with JSON only:
{{"mechanism": "one or two sentences",
  "body_part": "e.g. right knee",
  "side": "left / right / unknown",
  "severity": "Low / Medium / High / Critical",
  "urgency": "Emergency / Same day / Within 48 hours / Routine",
  "confidence": 0.0,
  "injuries": [{{"injury": "name", "likelihood": 0.0, "why": "visual reason"}}],
  "on_field": ["step", "step"],
  "tests": [{{"test": "e.g. MRI of the right knee", "why": "reason"}}],
  "treatment": ["step", "step"],
  "specialist": "who",
  "red_flags": ["sign", "sign"],
  "return_to_play": "guidance"}}
confidence is 0.0-1.0 for your overall assessment (below 0.6 when the clip is unclear)."""


def _make_config():
    kwargs = dict(response_mime_type="application/json", temperature=0.1)

    afc_cls = getattr(_types, "AutomaticFunctionCallingConfig", None)
    if afc_cls is not None:
        try:
            kwargs["automatic_function_calling"] = afc_cls(disable=True)
        except Exception:
            pass

    return _types.GenerateContentConfig(**kwargs)


def _ask(images, context, hints):
    global _models

    contents = []
    for label, data in images:
        contents.append(label)
        contents.append(_types.Part.from_bytes(data=data, mime_type="image/jpeg"))
    contents.append(_prompt(context, hints))

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


# ============================================
# TURN GEMINI'S ANSWER INTO THE STORED RESULT
# ============================================

def _text(v, n):
    v = str(v or "").strip()
    return v[:n] or None


def _texts(v, n_items, n_chars):
    out = []
    for item in (v if isinstance(v, list) else [v] if v else []):
        t = _text(item if not isinstance(item, dict) else (item.get("step") or item.get("text")), n_chars)
        if t:
            out.append(t)
        if len(out) >= n_items:
            break
    return out


def _as_float(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def _pick(value, allowed, default):
    v = str(value or "").strip().lower()
    for a in allowed:
        if a.lower() == v or a.lower() in v:
            return a
    return default


def interpret(raw):
    injuries = []
    for item in raw.get("injuries") or []:
        if not isinstance(item, dict):
            item = {"injury": item}
        name = _text(item.get("injury"), 80)
        if name:
            injuries.append({"injury": name, "likelihood": _as_float(item.get("likelihood")), "why": _text(item.get("why"), 200)})
        if len(injuries) >= 3:
            break

    tests = []
    for item in raw.get("tests") or []:
        if not isinstance(item, dict):
            item = {"test": item}
        name = _text(item.get("test"), 100)
        if name:
            tests.append({"test": name, "why": _text(item.get("why"), 200)})
        if len(tests) >= 5:
            break

    side = str(raw.get("side") or "").strip().lower()

    return {
        "mechanism": _text(raw.get("mechanism"), 400),
        "body_part": _text(raw.get("body_part"), 60),
        "side": side if side in ("left", "right") else None,
        "severity": _pick(raw.get("severity"), SEVERITIES, "Medium"),
        "urgency": _pick(raw.get("urgency"), URGENCIES, "Same day"),
        "confidence": _as_float(raw.get("confidence")),
        "injuries": injuries,
        "on_field": _texts(raw.get("on_field"), 6, 160),
        "tests": tests,
        "treatment": _texts(raw.get("treatment"), 6, 160),
        "specialist": _text(raw.get("specialist"), 120),
        "red_flags": _texts(raw.get("red_flags"), 5, 120),
        "return_to_play": _text(raw.get("return_to_play"), 200),
    }


def _patch(path, body):
    r = requests.patch(API_BASE + path, json=body, timeout=API_TIMEOUT)
    if r.status_code == 404:
        return {"action": "missing"}
    r.raise_for_status()
    return r.json()


def _alert_was_sent(event_id):
    try:
        import alert_system
        return event_id not in alert_system._duplicate_event_ids
    except Exception:
        return True


def _send_whatsapp(text):
    if not SEND_WHATSAPP:
        return
    try:
        import whatsapp_notifier
        whatsapp_notifier.send_message(text)
    except Exception as e:
        print("[TREATMENT-AI] WhatsApp message not sent:", e)


def whatsapp_message(event_id, context, r):
    lines = [
        "\U0001F3E5 AthleteGuard medical recommendation",
        "Event #" + str(event_id) + " - " + ((context or {}).get("player") or "Unidentified player"),
    ]
    if (context or {}).get("video_time"):
        lines.append("Video time: " + context["video_time"])
    lines.append("Severity: " + r["severity"] + " | Urgency: " + r["urgency"])
    if r.get("mechanism"):
        lines.append("Mechanism: " + r["mechanism"])
    if r["injuries"]:
        lines.append("")
        lines.append("Likely injuries:")
        for i in r["injuries"]:
            lines.append("- " + i["injury"] + (" (" + i["why"] + ")" if i.get("why") else ""))
    if r["on_field"]:
        lines.append("")
        lines.append("On the pitch now:")
        lines += ["- " + s for s in r["on_field"]]
    if r["tests"]:
        lines.append("")
        lines.append("Recommended tests:")
        lines += ["- " + t["test"] + (" - " + t["why"] if t.get("why") else "") for t in r["tests"]]
    if r["treatment"]:
        lines.append("")
        lines.append("Treatment:")
        lines += ["- " + s for s in r["treatment"]]
    if r.get("specialist"):
        lines.append("Specialist: " + r["specialist"])
    if r["red_flags"]:
        lines.append("Red flags (emergency care): " + "; ".join(r["red_flags"]))
    if r.get("return_to_play"):
        lines.append("Return to play: " + r["return_to_play"])
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def _process(job):
    ids, frames, target_index, box, context, hints = job
    event_id = ids[0]

    images = _build_images(frames, target_index, box)
    if not images:
        return

    r = interpret(_ask(images, context, hints))
    stats["checked"] += 1

    print(f"[TREATMENT-AI] #{event_id}: {r['severity']} / {r['urgency']} | "
          + (", ".join(i["injury"] for i in r["injuries"]) or "no injury named")
          + (" | tests: " + ", ".join(t["test"] for t in r["tests"]) if r["tests"] else ""))

    if not r["injuries"] and not r["tests"] and not r["on_field"]:
        return

    body = dict(r, model=_models[0] if _models else None)
    answer = _patch("/events/" + str(event_id) + "/ai-treatment", body)

    if answer.get("action") == "missing":
        return

    results[event_id] = body
    stats["stored"] += 1

    if _alert_was_sent(event_id):
        _send_whatsapp(whatsapp_message(event_id, context, r))