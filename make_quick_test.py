# Makes videos/fall_quick.mp4: two 1-minute parts of fall_test.mp4 that contain Ronaldo's falls
# (about 3:39 = low risk, about 34:29 = high risk), so the wristband can be tested in ~2 minutes.
# Run from D:\PROJECT\techno\Technovation-main :  python make_quick_test.py
import os
import sys
import cv2

SRC = os.path.join("videos", "fall_test.mp4")
OUT = os.path.join("videos", "fall_quick.mp4")
PARTS = [(200, 260), (2040, 2100)]      # (start, end) in seconds

cap = cv2.VideoCapture(SRC)
if not cap.isOpened():
    sys.exit("Cannot open " + SRC + " - run this from D:\\PROJECT\\techno\\Technovation-main")
fps = cap.get(cv2.CAP_PROP_FPS) or 30
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
out = cv2.VideoWriter(OUT, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

for start, end in PARTS:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
    for _ in range(int((end - start) * fps)):
        ok, frame = cap.read()
        if not ok:
            break
        out.write(frame)
    print("Copied", start, "s to", end, "s")

cap.release()
out.release()
print("Done:", OUT)