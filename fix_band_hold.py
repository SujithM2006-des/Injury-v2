# One-time patch (backend/main.py): after the match video finishes, the band keeps the colour it
# had at the end (falls reused from earlier runs stay counted during the hold time).
# Run from D:\PROJECT\techno\Technovation-main :  python fix_band_hold.py
import pathlib, shutil, sys

P = pathlib.Path("backend/main.py")
if not P.exists():
    sys.exit("main.py not found - run this from D:\\PROJECT\\techno\\Technovation-main")
raw = P.read_bytes().decode("utf-8")
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")

if "BAND HOLD FIX" in s:
    sys.exit("Already applied - nothing changed.")
if "BAND REUSE FIX" not in s:
    sys.exit("Run fix_band_reuse.py first - nothing changed.")

OLD = '        return info.get("match_id"), info.get("match_name"), "finished", None\n'
NEW = '''        # BAND HOLD FIX: keep counting up to where the video got to, so the colour stays the same
        video_end = None
        try:
            if progress.get("frame") is not None and info.get("fps"):
                video_end = float(progress["frame"]) / float(info["fps"])
        except (TypeError, ValueError, ZeroDivisionError):
            video_end = None
        return info.get("match_id"), info.get("match_name"), "finished", video_end
'''
if s.count(OLD) != 1:
    sys.exit("Your main.py is a different version than expected - nothing changed. Upload it again.")
s = s.replace(OLD, NEW)

shutil.copy(P, P.with_suffix(".py.bak_hold"))
if crlf:
    s = s.replace("\n", "\r\n")
P.write_bytes(s.encode("utf-8"))
print("Done: the band keeps its end-of-match colour during the hold time.")
print("Backup: backend/main.py.bak_hold  - restart the backend now.")