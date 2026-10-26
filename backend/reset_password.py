"""
Create a user or reset their password.

Usage (run from the backend folder):
    python reset_password.py <username> <new_password> [role] [team_name]

    role: admin / medical / coach (only needed when the user does not exist yet)
    team_name: required for a NEW coach (e.g. Netherlands)

Examples:
    python reset_password.py medical1 medical123 medical
    python reset_password.py coach1 coach1pass
    python reset_password.py --list
"""
import sys

from passlib.context import CryptContext

from crypto_store import lookup_hash
from database import SessionLocal
from models import User, Team

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ROLES = {"admin", "medical", "coach"}


def list_users(db):
    users = db.query(User).order_by(User.id).all()
    if not users:
        print("No users in the database.")
    for u in users:
        print(f"  id={u.id:<4} username={u.username!r:<20} role={u.role:<8} team_id={u.team_id}")


def main():
    db = SessionLocal()
    try:
        if len(sys.argv) == 2 and sys.argv[1] == "--list":
            list_users(db)
            return

        if len(sys.argv) < 3:
            print(__doc__)
            return

        username = sys.argv[1].strip()
        password = sys.argv[2]
        role = sys.argv[3].strip().lower() if len(sys.argv) > 3 else None
        team_name = sys.argv[4].strip() if len(sys.argv) > 4 else None

        if len(password) < 6:
            print("Password must be at least 6 characters.")
            return

        user = db.query(User).filter(User.username_lookup == lookup_hash(username)).first()

        if user is not None:
            user.password_hash = pwd_context.hash(password)
            db.commit()
            print(f"Password reset for {username!r} (role: {user.role}).")
            return

        # user does not exist -> create it
        if role not in ROLES:
            print(f"User {username!r} does not exist. Give a role to create it: admin / medical / coach")
            print("Existing users:")
            list_users(db)
            return

        team_id = None
        if role == "coach":
            team = next((t for t in db.query(Team).all() if t.name.lower() == team_name.lower()), None) if team_name else None
            if team is None:
                names = ", ".join(t.name for t in db.query(Team).all())
                print(f"A new coach needs a valid team name. Teams: {names}")
                return
            team_id = team.id

        db.add(User(username=username, password_hash=pwd_context.hash(password), role=role, team_id=team_id))
        db.commit()
        print(f"Created {role} user {username!r}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()