"""
fullscreen_window.py - one-time update (run it once, then delete it)

Makes the detection window resizable:
  - opens at about the same size as now
  - maximize button (the square next to X) -> full screen, click again -> back to normal
  - F key -> true full screen (no title bar), F again -> back to normal

Changes only src/multi_player_injury.py. Makes a .bak copy first, and changes
NOTHING if the file is not the version it expects.

Run it from the Technovation-main folder:
  python fullscreen_window.py
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

CHANGES = [
    ('src/multi_player_injury.py',
r'''# VIDEO LOOP

while True:
    ret, frame = cap.read()''',
r'''# DISPLAY WINDOW
# Resizable window that opens at about the same size as before.
#   - Maximize button (the square next to X): fills the screen, click it again to go back
#   - F key: true full screen without the title bar, press F again to go back
WINDOW_NAME = "AI Injury Detection v2"
WINDOW_WIDTH = 1100              # normal (not full screen) window width; height follows the video shape
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
_vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
_vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
_win_w = min(WINDOW_WIDTH, _vid_w)
_win_h = int(_win_w * _vid_h / _vid_w)
cv2.resizeWindow(WINDOW_NAME, _win_w, _win_h)
is_fullscreen = False
print("Window: maximize button or F = full screen (press again to go back)")

# VIDEO LOOP

while True:
    ret, frame = cap.read()'''),
    ('src/multi_player_injury.py',
r'''    cv2.imshow("AI Injury Detection v2", annotated_frame)
    key = cv2.waitKey(max(1, int(1000 / EFFECTIVE_FPS))) & 0xFF
    if key == ord("q"):
        print("Q pressed")
        break''',
r'''    cv2.imshow(WINDOW_NAME, annotated_frame)
    key = cv2.waitKey(max(1, int(1000 / EFFECTIVE_FPS))) & 0xFF
    if key == ord("q"):
        print("Q pressed")
        break
    if key == ord("f"):
        is_fullscreen = not is_fullscreen
        cv2.setWindowProperty(
            WINDOW_NAME, cv2.WND_PROP_FULLSCREEN,
            cv2.WINDOW_FULLSCREEN if is_fullscreen else cv2.WINDOW_NORMAL,
        )
        if not is_fullscreen:
            cv2.resizeWindow(WINDOW_NAME, _win_w, _win_h)'''),
]


def main():
    texts = {}
    crlf = {}
    for path in sorted({c[0] for c in CHANGES}):
        full = os.path.join(ROOT, *path.split("/"))
        if not os.path.isfile(full):
            print("NOT FOUND:", full)
            print("Run this script from the Technovation-main folder.")
            sys.exit(1)
        with open(full, "r", encoding="utf-8", newline="") as f:
            raw = f.read()
        crlf[path] = "\r\n" in raw
        texts[path] = raw.replace("\r\n", "\n")

    # check everything first, so nothing is half-changed
    problems = []
    for i, (path, old, new) in enumerate(CHANGES, 1):
        t = texts[path]
        if new in t and old not in t:
            problems.append("change %d in %s is already applied" % (i, path))
        elif t.count(old) != 1:
            problems.append("change %d in %s: expected text not found (file is a different version)" % (i, path))
    if problems:
        print("Nothing was changed:")
        for p in problems:
            print("  -", p)
        sys.exit(1)

    for path, old, new in CHANGES:
        texts[path] = texts[path].replace(old, new, 1)

    for path, t in texts.items():
        full = os.path.join(ROOT, *path.split("/"))
        shutil.copyfile(full, full + ".bak")
        if crlf[path]:
            t = t.replace("\n", "\r\n")
        with open(full, "w", encoding="utf-8", newline="") as f:
            f.write(t)
        print("Updated", path, "(backup:", os.path.basename(full) + ".bak)")

    print("Done. Start the detector again: cd src; python multi_player_injury.py")


if __name__ == "__main__":
    main()