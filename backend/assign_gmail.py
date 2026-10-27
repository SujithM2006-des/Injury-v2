"""
assign_gmail.py - give a Gmail a role, for "Sign in with Google" (Firebase).

Run from the backend folder (backend may keep running):
    python assign_gmail.py <gmail> <role> [team name | player name]
    python assign_gmail.py --list

    role: admin / medical / owner / coach / player
    coach / owner: also give the team, e.g.   python assign_gmail.py coach@gmail.com coach Portugal
    player:        also give the player,      python assign_gmail.py cr7@gmail.com player "Cristiano Ronaldo"

If a login with that Gmail exists, its role (and team / player) is changed.
Otherwise a new login is created (the Gmail is its username). Nobody gets a password:
they sign in with Google. (The admin keeps their own password login for emergencies.)
"""
import secrets
import sys

from passlib.context import CryptContext

from crypto_store import load_json, lookup_hash, save_json
from database import SessionLocal
from models import Player, Team, User
import os

ROLES = ("admin", "medical", "owner", "coach", "player")
PLAYER_ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "player_accounts.json")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def show(db):
    accounts = load_json(PLAYER_ACCOUNTS_FILE, {}) or {}
    players = {p.id: p.name for p in db.query(Player).all()}
    for u in sorted(db.query(User).all(), key=lambda u: (u.role, u.username.lower())):
        extra = (u.team.name if u.team else "") if u.role in ("coach", "owner") else players.get(accounts.get(str(u.id)), "") if u.role == "player" else ""
        print(f"  {u.role:8} {u.email or '(no Gmail - password login only)':38} {u.username:28} {extra}")


def main():
    db = SessionLocal()
    try:
        if len(sys.argv) == 2 and sys.argv[1] == "--list":
            return show(db)
        if len(sys.argv) < 3:
            print(__doc__)
            return
        email, role = sys.argv[1].strip().lower(), sys.argv[2].strip().lower()
        extra = " ".join(sys.argv[3:]).strip()
        if "@" not in email or "." not in email.split("@")[-1]:
            sys.exit("Not a valid Gmail address: " + email)
        if role not in ROLES:
            sys.exit("Role must be one of: " + ", ".join(ROLES))

        team_id, player = None, None
        if role in ("coach", "owner"):
            team = next((t for t in db.query(Team).all() if t.name.lower() == extra.lower()), None)
            if team is None:
                sys.exit(f"A {role} needs a team. Teams: " + ", ".join(t.name for t in db.query(Team).all()))
            team_id = team.id
        if role == "player":
            player = next((p for p in db.query(Player).all() if p.name.lower() == extra.lower()), None)
            if player is None:
                sys.exit("A player login needs the roster player's exact name, e.g. \"Cristiano Ronaldo\"")
            team_id = player.team_id

        user = db.query(User).filter(User.email_lookup == lookup_hash(email)).first()
        if user is None:
            if db.query(User).filter(User.username_lookup == lookup_hash(email)).first() is not None:
                sys.exit("A login with the username " + email + " already exists without this Gmail.")
            user = User(username=email, password_hash=pwd.hash(secrets.token_urlsafe(32)), role=role, team_id=team_id)
            user.set_email(email)
            db.add(user)
            action = "created"
        else:
            user.role, user.team_id = role, team_id
            action = "updated"
        db.commit()
        db.refresh(user)

        accounts = load_json(PLAYER_ACCOUNTS_FILE, {}) or {}
        accounts.pop(str(user.id), None)
        if player is not None:
            for k, v in list(accounts.items()):
                if v == player.id:
                    accounts.pop(k)          # one login per player
            accounts[str(user.id)] = player.id
        save_json(PLAYER_ACCOUNTS_FILE, accounts)

        print(f"{action}: {email} -> {role}" + (f" ({extra})" if extra else "") + ". They can now use 'Sign in with Google'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
