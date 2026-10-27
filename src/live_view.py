# ============================================
# LIVE VIEW
# Sends the detector's annotated frames (boxes, skeletons, "REGION | RISK")
# to the backend, so every logged-in user sees the detection live on the
# website (dashboard + match monitor) instead of a separate Python window.
#
# Safe by design (like system_status.py):
#   - the detection loop only hands over its newest frame (no copy, no wait)
#   - one background thread resizes, JPEG-encodes and posts at most LIVE_FPS
#   - frames that arrive while a post is in progress are skipped, never queued
#   - if the backend is down it prints one warning and carries on
# ============================================

import threading
import time

import cv2
import requests

API_BASE = "http://127.0.0.1:8000"
LIVE_FPS = 12            # frames per second sent to the website
LIVE_WIDTH = 960         # frames are downscaled to this width
JPEG_QUALITY = 70
REQUEST_TIMEOUT = 2

_lock = threading.Lock()
_wake = threading.Event()
_stop = threading.Event()
_latest = None
_thread = None
_warned = False


def _send(frame):
    global _warned
    h, w = frame.shape[:2]
    if w > LIVE_WIDTH:
        frame = cv2.resize(frame, (LIVE_WIDTH, int(h * LIVE_WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        return
    try:
        requests.post(API_BASE + "/live/frame", data=buf.tobytes(),
                      headers={"Content-Type": "image/jpeg"}, timeout=REQUEST_TIMEOUT)
        _warned = False
    except Exception as e:
        if not _warned:
            print("[LIVE] Could not send the live view to the website (detection continues):", e)
            _warned = True


def _loop():
    global _latest
    gap = 1.0 / LIVE_FPS
    while not _stop.is_set():
        _wake.wait(1.0)
        _wake.clear()
        with _lock:
            frame, _latest = _latest, None
        if frame is None:
            continue
        started = time.perf_counter()
        _send(frame)
        rest = gap - (time.perf_counter() - started)
        if rest > 0:
            _stop.wait(rest)


def start():
    global _thread
    if _thread is not None:
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()
    print("[LIVE] Live view on the website: on (" + str(LIVE_FPS) + " fps)")


def push(frame):
    """Hand over the newest annotated frame. Cheap: only keeps a reference."""
    global _latest
    with _lock:
        _latest = frame
    _wake.set()


def stop():
    _stop.set()
    _wake.set()
