# One-time patch: smoother detection on the GPU
#  1. FP16 (half precision) on the GPU - the RTX tensor cores run the pose model about 2x faster
#  2. Video frames are read in a background thread, so the GPU never waits for the next frame
#  3. The window no longer adds a fixed 33 ms pause on top of each frame (it only waits what is left)
#  4. Per-frame [DEBUG] printing off (summaries at the end still print)
# Run from D:\PROJECT\techno\Technovation-main :  python gpu_boost.py
import pathlib, shutil, sys

P = pathlib.Path("src/multi_player_injury.py")
if not P.exists():
    sys.exit("multi_player_injury.py not found - run this from D:\\PROJECT\\techno\\Technovation-main")
raw = P.read_bytes().decode("utf-8")
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")

if "GPU BOOST" in s:
    sys.exit("Already applied - nothing changed.")

READER = '''# GPU BOOST: read frames in a background thread so the GPU never waits for the next frame.
# Video files: every frame is kept (nothing skipped). Webcam / capture card: always the newest frame.
import queue as _q
import time as _time


class _ThreadedCapture:
    def __init__(self, cap, live):
        self.cap = cap
        self.live = live
        self.q = _q.Queue(maxsize=2 if live else 64)
        self.stopped = False
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def _run(self):
        while not self.stopped:
            ok, frame = self.cap.read()
            if self.live and self.q.full():
                try:
                    self.q.get_nowait()
                except _q.Empty:
                    pass
            self.q.put((ok, frame))
            if not ok:
                break

    def read(self):
        return self.q.get()

    def get(self, prop):
        return self.cap.get(prop)

    def isOpened(self):
        return self.cap.isOpened()

    def release(self):
        self.stopped = True
        try:
            while True:
                self.q.get_nowait()
        except _q.Empty:
            pass
        self.t.join(timeout=2)
        self.cap.release()


cap = _ThreadedCapture(open_video_source(), SOURCE_MODE in ("webcam", "capture_card"))
'''

edits = [
    ("DEBUG_FALL_METRICS = True\n", "DEBUG_FALL_METRICS = False   # GPU BOOST: True prints every player every frame (slow)\n"),
    ("cap = open_video_source()\n", READER),
    ("        tracker=TRACKER_CONFIG,\n    )\n    result = results[0]\n",
     "        tracker=TRACKER_CONFIG,\n        half=(DEVICE == 0),   # GPU BOOST: FP16 on the GPU\n    )\n    result = results[0]\n"),
    ("    cv2.imshow(WINDOW_NAME, annotated_frame)\n    key = cv2.waitKey(max(1, int(1000 / EFFECTIVE_FPS))) & 0xFF\n",
     "    cv2.imshow(WINDOW_NAME, annotated_frame)\n"
     "    # GPU BOOST: wait only for the time left in this frame, not a full extra frame\n"
     "    _now = _time.perf_counter()\n"
     "    _left_ms = int((1.0 / EFFECTIVE_FPS - (_now - globals().get('_last_frame_t', _now))) * 1000)\n"
     "    key = cv2.waitKey(max(1, _left_ms)) & 0xFF\n"
     "    _last_frame_t = _time.perf_counter()\n"),
]
for old, _ in edits:
    if s.count(old) != 1:
        sys.exit("Your multi_player_injury.py is a different version than expected - nothing changed. Upload it again.")
for old, new in edits:
    s = s.replace(old, new)

shutil.copy(P, P.with_suffix(".py.bak2"))
if crlf:
    s = s.replace("\n", "\r\n")
P.write_bytes(s.encode("utf-8"))
print("Done: FP16 on the GPU, background frame reading, no extra wait, debug printing off.")
print("Backup: src/multi_player_injury.py.bak2")