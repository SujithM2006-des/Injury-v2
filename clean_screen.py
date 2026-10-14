"""
clean_screen.py - one-time update (run it once, then delete it)

Removes the status text from the detection window and the saved clips:
  "NO PLAYER DETECTED", "NO VALID PLAYER", "NOT GAMEPLAY (close-up / crowd) ..."
  and "AI INJURY DETECTION v2 | <match>".
Player boxes, skeletons and names stay. Detection itself is not changed.
To show the text again later, set SHOW_STATUS_TEXT = True in src/multi_player_injury.py.

Changes only src/multi_player_injury.py. Makes a .bak copy first, and changes
NOTHING if the file is not the version it expects.

Run it from the Technovation-main folder:
  python clean_screen.py
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

CHANGES = [
    ('src/multi_player_injury.py',
r'''        if not any_valid_player_this_frame:
            cv2.putText(
                annotated_frame, "NO VALID PLAYER",
                (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2
            )
    else:
        cv2.putText(
            annotated_frame, "NO PLAYER DETECTED",
            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2
        )
''',
r'''        if SHOW_STATUS_TEXT and not any_valid_player_this_frame:
            cv2.putText(
                annotated_frame, "NO VALID PLAYER",
                (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2
            )
    elif SHOW_STATUS_TEXT:
        cv2.putText(
            annotated_frame, "NO PLAYER DETECTED",
            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2
        )
'''),
    ('src/multi_player_injury.py',
r'''    banner_y = annotated_frame.shape[0] - 20
    cv2.putText(
        annotated_frame, "AI INJURY DETECTION v2 | " + display_text(MATCH_NAME),
        (20, banner_y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
    )
    if not is_gameplay_shot:
        cv2.putText(''',
r'''    banner_y = annotated_frame.shape[0] - 20
    if SHOW_STATUS_TEXT:
        cv2.putText(
            annotated_frame, "AI INJURY DETECTION v2 | " + display_text(MATCH_NAME),
            (20, banner_y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
        )
    if SHOW_STATUS_TEXT and not is_gameplay_shot:
        cv2.putText('''),
    ('src/multi_player_injury.py',
r'''# DEBUG SETTINGS
DEBUG_FALL_METRICS = True''',
r'''# DEBUG SETTINGS
DEBUG_FALL_METRICS = True

# On-screen status text ("NO PLAYER DETECTED", "NOT GAMEPLAY ...", "AI INJURY DETECTION v2 | match").
# False = clean video (also in the saved clips). Detection itself is not affected.
SHOW_STATUS_TEXT = False'''),
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