# One-time patch (backend/main.py): the wristband starts BLUE on every new run of a video.
#  - Falls from earlier runs of the same video count only when the video reaches their time,
#    and never while the current video time is unknown (detector still starting).
#  - Only real detector falls are reused from earlier runs (no manual / "TEST" events).
#  - The same fall saved by several earlier runs is counted once.
#  - /band/{id}/summary now also lists the counted events (id, video time, match) to check it.
# Run from D:\PROJECT\techno\Technovation-main :  python fix_band_reuse.py
import pathlib, shutil, sys

P = pathlib.Path("backend/main.py")
if not P.exists():
    sys.exit("main.py not found - run this from D:\\PROJECT\\techno\\Technovation-main")
raw = P.read_bytes().decode("utf-8")
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")

if "BAND REUSE FIX" in s:
    sys.exit("Already applied - nothing changed.")

START = "def _band_events(db, match_id, video_now):\n"
END = "def _band_level(high, medium, low):\n"

NEW_EVENTS = '''def _band_is_test(e):
    text = ((e.note or "") + " " + (e.injury_note or "")).lower()
    return "test only" in text or text.strip().startswith("test")


def _band_events(db, match_id, video_now):
    """BAND REUSE FIX: falls of this match + real detector falls of earlier runs of the same video
    that the video has already reached. Each fall is counted once."""
    rows = [e for e in db.query(InjuryEvent).filter(InjuryEvent.match_session_id == match_id).all()
            if not _band_is_test(e)]
    key_of = globals().get("_video_key")
    match = db.query(MatchSession).filter(MatchSession.id == match_id).first()
    key = key_of(match) if (key_of and match) else None
    if key and video_now is not None:
        seen = {e.id for e in rows}
        earlier = (db.query(InjuryEvent)
                   .filter(InjuryEvent.match_session_id.isnot(None),
                           InjuryEvent.match_session_id != match_id,
                           InjuryEvent.video_time_sec.isnot(None))
                   .order_by(InjuryEvent.timestamp.desc())
                   .all())
        for e in earlier:
            if e.id in seen or key_of(e.match) != key:
                continue
            if (e.source or "ai") != "ai" or _band_is_test(e):
                continue      # only real detector falls are reused
            if e.video_time_sec > video_now + 1:
                continue      # the video has not reached this fall yet
            rows.append(e)
    # the same fall saved by several runs counts once (this run first, then the newest earlier run)
    window = globals().get("DUPLICATE_WINDOW_SEC", 3)
    kept = []
    for e in rows:
        dup = e.video_time_sec is not None and any(
            k.video_time_sec is not None
            and abs(k.video_time_sec - e.video_time_sec) <= window
            and (k.event_type or "").upper() == (e.event_type or "").upper()
            and (k.player_id is None or e.player_id is None or k.player_id == e.player_id)
            for k in kept)
        if not dup:
            kept.append(e)
    return kept


'''

OLD_LOOP = "        for e in _band_events(db, match_id, video_now):\n            if player_id and e.player_id != player_id:\n                continue\n            if (e.gemini_verdict or \"\") == \"false_alarm\":\n                continue\n            risk = (e.risk or \"\").upper()\n            if risk not in counts:\n                continue\n            counts[risk] += 1\n"
NEW_LOOP = "        for e in _band_events(db, match_id, video_now):\n            if player_id and e.player_id != player_id:\n                continue\n            if (e.gemini_verdict or \"\") == \"false_alarm\":\n                continue\n            risk = (e.risk or \"\").upper()\n            if risk not in counts:\n                continue\n            counts[risk] += 1\n            counted.append({\"id\": e.id, \"match_id\": e.match_session_id, \"video_time_sec\": e.video_time_sec,\n                            \"risk\": risk, \"player_id\": e.player_id, \"source\": e.source})\n"

OLD_INIT = "    per_player = {}            # player id (None = Unidentified) -> name, jersey, team, counts\n"
NEW_INIT = OLD_INIT + "    counted = []               # the events behind the colour (shown in /summary)\n"

OLD_RET = "            \"low\": counts[\"LOW\"], \"match_id\": match_id, \"match_name\": match_name, \"match_state\": state,\n            \"players\": players}\n"
NEW_RET = "            \"low\": counts[\"LOW\"], \"match_id\": match_id, \"match_name\": match_name, \"match_state\": state,\n            \"video_now\": round(video_now, 1) if video_now is not None else None,\n            \"players\": players, \"events\": counted}\n"

if s.count(START) != 1 or s.count(END) != 1 or s.index(START) > s.index(END):
    sys.exit("Your main.py is a different version than expected - nothing changed. Upload it again.")
for old in (OLD_LOOP, OLD_INIT, OLD_RET):
    if s.count(old) != 1:
        sys.exit("Your main.py is a different version than expected - nothing changed. Upload it again.")

i, j = s.index(START), s.index(END)
s = s[:i] + NEW_EVENTS + s[j:]
s = s.replace(OLD_LOOP, NEW_LOOP).replace(OLD_INIT, NEW_INIT).replace(OLD_RET, NEW_RET)

shutil.copy(P, P.with_suffix(".py.bak_band"))
if crlf:
    s = s.replace("\n", "\r\n")
P.write_bytes(s.encode("utf-8"))
print("Done: the band starts blue on every new run and counts each real fall once.")
print("Backup: backend/main.py.bak_band  - restart the backend now.")