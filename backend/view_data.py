"""
view_data.py - print the database DECRYPTED (needs ATHLETEGUARD_DATA_KEY in .env).

Run from the backend folder:
    python view_data.py                 summary of every table
    python view_data.py teams           all teams
    python view_data.py players         all players
    python view_data.py users           all logins (password hashes are not shown)
    python view_data.py matches         all match sessions
    python view_data.py events          all injury events
    python view_data.py events 20       only the newest 20 events
    python view_data.py event 412       one event with every field
"""

import sys

from database import SessionLocal
from models import InjuryEvent, MatchSession, Player, Team, User


def table(rows, cols):
    if not rows:
        print("(no rows)")
        return
    text = [[("" if r.get(c) is None else str(r.get(c))) for c in cols] for r in rows]
    width = [min(40, max(len(c), *(len(t[i]) for t in text))) for i, c in enumerate(cols)]
    print("  ".join(c.ljust(w) for c, w in zip(cols, width)))
    print("  ".join("-" * w for w in width))
    for t in text:
        print("  ".join(v[:w].ljust(w) for v, w in zip(t, width)))
    print(f"\n{len(rows)} row(s)")


def main():
    what = sys.argv[1].lower() if len(sys.argv) > 1 else "summary"
    arg = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None
    db = SessionLocal()
    try:
        teams = {t.id: t.name for t in db.query(Team).all()}

        if what == "summary":
            for name, model in (("teams", Team), ("players", Player), ("users", User),
                                ("match_sessions", MatchSession), ("injury_events", InjuryEvent)):
                print(f"{name:15} {db.query(model).count()} row(s)")
            print("\nDetails: python view_data.py teams | players | users | matches | events [N] | event <id>")

        elif what == "teams":
            table([{"id": i, "name": n} for i, n in sorted(teams.items())], ["id", "name"])

        elif what == "players":
            rows = sorted(db.query(Player).all(), key=lambda p: (p.team_id, p.jersey_number))
            table([{"id": p.id, "team": teams.get(p.team_id), "jersey": p.jersey_number, "name": p.name} for p in rows],
                  ["id", "team", "jersey", "name"])

        elif what == "users":
            rows = sorted(db.query(User).all(), key=lambda u: (u.role, u.username.lower()))
            table([{"id": u.id, "username": u.username, "role": u.role, "team": teams.get(u.team_id)} for u in rows],
                  ["id", "username", "role", "team"])

        elif what == "matches":
            rows = db.query(MatchSession).order_by(MatchSession.id.desc()).all()
            table([{"id": m.id, "name": m.name, "date": m.date and m.date.strftime("%Y-%m-%d %H:%M"),
                    "video": m.video_source} for m in rows], ["id", "name", "date", "video"])

        elif what == "events":
            q = db.query(InjuryEvent).order_by(InjuryEvent.id.desc())
            rows = q.limit(arg).all() if arg else q.all()
            table([{"id": e.id, "match": e.match_session_id, "player": e.player.name if e.player else "Unidentified",
                    "type": e.event_type, "region": e.region, "risk": e.risk,
                    "video_s": e.video_time_sec, "by": e.identified_by, "reviewed": e.resolved,
                    "when": e.timestamp and e.timestamp.strftime("%Y-%m-%d %H:%M")} for e in rows],
                  ["id", "match", "player", "type", "region", "risk", "video_s", "by", "reviewed", "when"])

        elif what == "event" and arg:
            e = db.query(InjuryEvent).filter(InjuryEvent.id == arg).first()
            if e is None:
                print("No event", arg)
                return
            for c in InjuryEvent.__table__.columns:
                print(f"{c.name:26} {getattr(e, c.name)}")
            print(f"{'player name':26} {e.player.name if e.player else 'Unidentified'}")

        else:
            print(__doc__)
    finally:
        db.close()


if __name__ == "__main__":
    main()
