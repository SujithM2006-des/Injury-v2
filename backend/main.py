import os
import sys
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from pydantic import BaseModel
import base64
import re
import secrets

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, object_session
from sqlalchemy.sql import func

from database import get_db, SessionLocal, Base
from models import User, Player, InjuryEvent, Team, MatchSession
from auth import verify_password, create_access_token, decode_access_token
from crypto_store import encrypt_text, loads_maybe_encrypted, lookup_hash, now_utc, session_key
from crypto_store import load_json as _crypto_load_json, save_json as _crypto_save_json
from secure_transport import SecureTransport


app = FastAPI()

# encrypts every logged-in JSON response for the dashboard (added first, so CORS stays outermost)
app.add_middleware(SecureTransport)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS_DIR = os.path.join(PROJECT_ROOT, "output", "clips")
os.makedirs(CLIPS_DIR, exist_ok=True)

app.mount("/clips", StaticFiles(directory=CLIPS_DIR), name="clips")


# ============================================
# STARTUP BOOTSTRAP (replaces create_tables, migrate_v2,
# seed_match_2006, ensure_users, create_admin, add_players)
# Only adds what is missing. Never deletes anything and
# never changes an existing password.
# Older databases are upgraded to the encrypted schema by encrypt_database.py.
# ============================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---- encrypted columns cannot be compared in SQL: look rows up in Python ----

def _team_named(db, name):
    wanted = str(name or "").strip().lower()
    return next((t for t in db.query(Team).order_by(Team.id).all() if (t.name or "").strip().lower() == wanted), None)


def _user_named(db, username):
    return db.query(User).filter(User.username_lookup == lookup_hash(username)).first()


def _norm_code(value):
    """Event types and body regions are stored in one style: "fall" / " left leg" -> "FALL" / "LEFT LEG"."""
    text_value = " ".join(str(value or "").split()).upper()
    return text_value or None


def _players_of_team(db, team_id):
    return [p for p in db.query(Player).all() if p.team_id == team_id]


def _events_of_match(db, match_id):
    return [e for e in db.query(InjuryEvent).filter(InjuryEvent.match_session_id.isnot(None)).all()
            if e.match_session_id == match_id]


def _check_encryption_ready(engine):
    """Stops the backend with a clear message when the key or the encrypted schema is missing."""
    encrypt_text("check")
    insp = inspect(engine)
    tables = insp.get_table_names()
    users_ready = "users" not in tables or "username_lookup" in {c["name"] for c in insp.get_columns("users")}
    links_ready = "injury_events" not in tables or any(
        c["name"] == "player_id" and str(c["type"]).upper() == "TEXT" for c in insp.get_columns("injury_events"))
    if not (users_ready and links_ready):
        raise RuntimeError("The database is not (fully) encrypted yet. Stop the backend and run once (backend folder):  "
                           "python encrypt_database.py")
    # Gmail for "Sign in with Google" (added later): only adds what is missing
    if "users" in tables and "email_lookup" not in {c["name"] for c in insp.get_columns("users")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_lookup VARCHAR(64)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_lookup ON users (email_lookup)"))
        print("[BOOTSTRAP] added the Gmail columns for Google sign-in")

# ============================================
# GEMINI RULES
# false alarm with at least this confidence -> event is deleted (clip too)
# Gemini's jersey read replaces ours only if it is at least this sure
# AND more confident than our own identification
# ============================================

GEMINI_DELETE_MIN_CONFIDENCE = 0.75
GEMINI_JERSEY_MIN_CONFIDENCE = 0.60

# ============================================
# DUPLICATE FALLS
# Running the detector on the same video again creates a new match session
# and would save every fall a second time. Two AI events are the SAME fall when:
#   - they come from DIFFERENT runs (match sessions) of the SAME video file
#   - same event type
#   - their times in the video are within DUPLICATE_WINDOW_SEC
#   - same player if both are identified; otherwise same track id or same body area
# Falls inside one run are never merged (two players can fall at the same moment).
# ============================================

DUPLICATE_WINDOW_SEC = 3.0

ROSTERS = {
    "Portugal": [
        (1, "Ricardo"),
        (5, "Fernando Meira"),
        (6, "Costinha"),
        (7, "Lu\u00eds Figo"),
        (8, "Petit"),
        (9, "Pauleta"),
        (11, "Sim\u00e3o"),
        (13, "Miguel"),
        (14, "Nuno Valente"),
        (16, "Ricardo Carvalho"),
        (17, "Cristiano Ronaldo"),
        (18, "Maniche"),
        (19, "Tiago"),
        (20, "Deco"),
    ],
    "Netherlands": [
        (1, "Edwin van der Sar"),
        (3, "Khalid Boulahrouz"),
        (4, "Joris Mathijsen"),
        (5, "Giovanni van Bronckhorst"),
        (7, "Dirk Kuyt"),
        (8, "Phillip Cocu"),
        (10, "Rafael van der Vaart"),
        (11, "Arjen Robben"),
        (13, "Andr\u00e9 Ooijer"),
        (14, "John Heitinga"),
        (17, "Robin van Persie"),
        (18, "Mark van Bommel"),
        (19, "Jan Vennegoor of Hesselink"),
        (20, "Wesley Sneijder"),
    ],
}

PLACEHOLDER_TEAMS = {"Portugal": "Team A", "Netherlands": "Team B"}

# Demo logins (username + password, next to Sign in with Google).
# Created if missing and their password is set back to this one on every start.
# (username, role, team, password); a player login belongs to the roster player (team, jersey)
DEMO_ACCOUNTS = [
    ("admin", "admin", None, "admin123"),
    ("medical1", "medical", None, "medical123"),
    ("CR7", "player", ("Portugal", 17), "123456"),
    ("owner1", "owner", "Portugal", "owner123"),
    ("coach1", "coach", "Netherlands", "coach123"),
    ("coach2", "coach", "Portugal", "coach123"),
]


def bootstrap_data():

    probe = SessionLocal()
    engine = probe.get_bind()
    probe.close()

    # 1. key + encrypted schema, then any missing tables
    _check_encryption_ready(engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # 2. teams + players
        teams = {}

        for team_name, roster in ROSTERS.items():

            team = _team_named(db, team_name)

            if team is None:
                placeholder = _team_named(db, PLACEHOLDER_TEAMS[team_name])
                if placeholder is not None:
                    placeholder.name = team_name
                    team = placeholder

            if team is None:
                team = Team(name=team_name)
                db.add(team)
                db.flush()

            teams[team_name] = team

            existing = {}
            for p in _players_of_team(db, team.id):
                existing.setdefault(p.jersey_number, p)

            for number, name in roster:
                if number not in existing:
                    db.add(Player(team_id=team.id, name=name, jersey_number=number))
                    print("[BOOTSTRAP] added player:", team_name, "#" + str(number), name)

        db.flush()

        # 3. demo accounts (password login)
        player_links = {}

        for username, role, where, password in DEMO_ACCOUNTS:

            player = None
            team_id = None

            if role == "player":
                team_name, jersey = where
                player = next((p for p in _players_of_team(db, teams[team_name].id) if p.jersey_number == jersey), None)
                team_id = teams[team_name].id
            elif where is not None:
                team_id = teams[where].id

            user = _user_named(db, username)

            if user is None:
                user = User(username=username, password_hash=pwd_context.hash(password), role=role, team_id=team_id)
                db.add(user)
                db.flush()
                print("[BOOTSTRAP] created", username, "(" + role + ") | password:", password)

            else:
                if not verify_password(password, user.password_hash):
                    user.password_hash = pwd_context.hash(password)
                    print("[BOOTSTRAP] demo password set for", username)
                if user.role != role or user.team_id != team_id:
                    user.role = role
                    user.team_id = team_id
                    print("[BOOTSTRAP] assigned", username, "->", role, where or "")

            if player is not None:
                player_links[str(user.id)] = player.id

        if player_links:
            accounts = _player_accounts()
            if any(accounts.get(k) != v for k, v in player_links.items()):
                accounts.update(player_links)
                _save_json(PLAYER_ACCOUNTS_FILE, accounts)

        # 4. admin (only if none exists)
        if not any(u.role == "admin" for u in db.query(User).all()):
            db.add(User(
                username="admin1",
                password_hash=pwd_context.hash("admin1pass"),
                role="admin",
                team_id=None,
            ))
            print("[BOOTSTRAP] created admin1 | password: admin1pass")

        db.commit()

        print("[BOOTSTRAP] done:", db.query(Player).count(), "players,", db.query(User).count(), "users")

    except Exception as e:
        db.rollback()
        print("[BOOTSTRAP] failed:", e)

    finally:
        db.close()


def _video_key(match):
    """Same video file = same key (case and slash direction ignored)."""
    if match is None or not match.video_source:
        return None
    return str(match.video_source).strip().replace("\\", "/").lower()


def _same_fall(a, b, key_a=None):
    """True if events a and b are the same fall from two runs of the same video.
    key_a: video key of a, when a is not saved yet (no .match loaded)."""

    if a.match_session_id is None or b.match_session_id is None:
        return False
    if a.match_session_id == b.match_session_id:
        return False
    if (a.source or "ai") != "ai" or (b.source or "ai") != "ai":
        return False
    if a.video_time_sec is None or b.video_time_sec is None:
        return False
    if key_a is None:
        key_a = _video_key(a.match)
    if key_a is None or key_a != _video_key(b.match):
        return False
    if (a.event_type or "").upper() != (b.event_type or "").upper():
        return False
    if abs(a.video_time_sec - b.video_time_sec) > DUPLICATE_WINDOW_SEC:
        return False

    if a.player_id is not None and b.player_id is not None:
        return a.player_id == b.player_id

    same_track = a.track_id is not None and a.track_id == b.track_id
    same_area = bool(a.region) and (a.region or "").upper() == (b.region or "").upper()
    return same_track or same_area


def _keep_score(e):
    """Which copy of a duplicate to keep: the newest (the latest run replaces earlier ones)."""
    return e.id


def _clip_exists(clip_path):
    return bool(clip_path) and os.path.exists(os.path.join(CLIPS_DIR, clip_path))


def _remove_clip_file(clip_path):
    if not clip_path:
        return
    try:
        os.remove(os.path.join(CLIPS_DIR, clip_path))
    except OSError:
        pass


def _clip_used_by_other_event(db, clip_path, exclude_ids):
    """One clip file can belong to several events (players who fell in the same frame)."""
    if not clip_path:
        return False
    q = db.query(InjuryEvent).filter(InjuryEvent.clip_path.isnot(None))
    if exclude_ids:
        q = q.filter(InjuryEvent.id.notin_(list(exclude_ids)))
    return any(e.clip_path == clip_path for e in q.all())


def remove_duplicate_events(db, dry_run=False):
    """
    Keeps one event per fall and deletes the extra copies (and their clip files).
    Returns a list of {"kept": id, "removed": [ids]}.
    """

    events = (
        db.query(InjuryEvent)
        .filter(InjuryEvent.match_session_id.isnot(None), InjuryEvent.video_time_sec.isnot(None))
        .all()
    )
    events = [e for e in events if (e.source or "ai") == "ai" and _video_key(e.match)]
    events.sort(key=_keep_score, reverse=True)

    clusters = []   # each: {"keeper": event, "members": [events], "sessions": set()}

    for e in events:
        home = None
        for c in clusters:
            if e.match_session_id in c["sessions"]:
                continue
            if _same_fall(c["keeper"], e):
                home = c
                break
        if home is None:
            clusters.append({"keeper": e, "members": [e], "sessions": {e.match_session_id}})
        else:
            home["members"].append(e)
            home["sessions"].add(e.match_session_id)

    report = []

    for c in clusters:
        if len(c["members"]) < 2:
            continue

        keeper = c["keeper"]
        extras = [m for m in c["members"] if m.id != keeper.id]

        report.append({"kept": keeper.id, "removed": [m.id for m in extras]})

        if dry_run:
            continue

        # the kept event takes a working clip from a copy if its own is missing
        if not _clip_exists(keeper.clip_path):
            for m in extras:
                if _clip_exists(m.clip_path):
                    keeper.clip_path = m.clip_path
                    break

        extra_ids = [m.id for m in extras]
        for m in extras:
            if (m.clip_path and m.clip_path != keeper.clip_path
                    and not _clip_used_by_other_event(db, m.clip_path, extra_ids)):
                _remove_clip_file(m.clip_path)
            db.delete(m)

    if not dry_run and report:
        db.commit()

    return report


def _cleanup_duplicates_on_startup():
    db = SessionLocal()
    try:
        report = remove_duplicate_events(db)
        removed = sum(len(r["removed"]) for r in report)
        if removed:
            print("[DUPLICATES] Removed", removed, "duplicate event(s):", report)
        else:
            print("[DUPLICATES] No duplicate events found")
    except Exception as e:
        db.rollback()
        print("[DUPLICATES] Cleanup skipped:", e)
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    bootstrap_data()
    _cleanup_duplicates_on_startup()


# ============================================
# REQUEST SCHEMAS
# ============================================

class LoginRequest(BaseModel):
    username: str
    password: str


class EventCreateRequest(BaseModel):
    player_id: Optional[int] = None          # None = Unidentified
    match_session_id: Optional[int] = None
    event_type: str
    region: Optional[str] = None
    risk: Optional[str] = None
    movement: Optional[float] = None
    injury_note: Optional[str] = None
    clip_path: Optional[str] = None
    source: str = "ai"
    track_id: Optional[int] = None
    video_time_sec: Optional[float] = None
    identified_by: Optional[str] = None      # jersey / jersey_name / jersey_history / jersey_handoff / face
    id_detail: Optional[str] = None          # e.g. "jersey #17", "face match (3 frames)"
    id_confidence: Optional[float] = None    # 0..1


class EventAIUpdateRequest(BaseModel):
    player_id: Optional[int] = None
    clip_path: Optional[str] = None
    injury_note: Optional[str] = None
    identified_by: Optional[str] = None
    id_detail: Optional[str] = None
    id_confidence: Optional[float] = None


class AssignPlayerRequest(BaseModel):
    player_id: int


class GeminiResultRequest(BaseModel):
    verdict: str                                  # real_fall / false_alarm / unsure / error
    confidence: Optional[float] = None            # 0..1, confidence in the verdict
    reason: Optional[str] = None
    description: Optional[str] = None
    team: Optional[str] = None                    # "Portugal" / "Netherlands" / "unknown"
    jersey_number: Optional[int] = None
    jersey_confidence: Optional[float] = None     # 0..1


class ManualEventRequest(BaseModel):
    player_id: int
    event_type: str
    note: str
    risk: Optional[str] = "MEDIUM"
    match_session_id: Optional[int] = None


class MatchCreateRequest(BaseModel):
    name: Optional[str] = None
    video_source: Optional[str] = None


# ============================================
# AUTH DEPENDENCY
# ============================================

def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):

    # no / wrong header -> 401 (not 422), so the dashboard sends the user to the login page
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.replace("Bearer ", "")

    payload = decode_access_token(token)

    # tokens from before encryption have no session id -> log in again
    if payload is None or not payload.get("sid"):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == payload.get("user_id")).first()

    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# ============================================
# GEMINI INJURY CHECK RESULTS (src/gemini_injury.py)
# Possible injuries + rest time per event, kept in output/ai_injury.json
# (no database change). Read again only when the file changes.
# ============================================

import json as _json

AI_INJURY_FILE = os.path.join(PROJECT_ROOT, "output", "ai_injury.json")
_ai_injury_cache = {"mtime": None, "data": {}}


def _ai_injury_all():
    try:
        st = os.stat(AI_INJURY_FILE)
        mtime = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _ai_injury_cache["mtime"] != mtime:
        try:
            with open(AI_INJURY_FILE, "r", encoding="utf-8") as f:
                _ai_injury_cache["data"] = loads_maybe_encrypted(f.read())
        except Exception:          # missing, damaged or encrypted with another key: no AI results
            _ai_injury_cache["data"] = {}
        _ai_injury_cache["mtime"] = mtime
    return _ai_injury_cache["data"]


def _ai_injury_for(event_id):
    return _ai_injury_all().get(str(event_id))


# Medical recommendation per event (src/gemini_treatment.py, KEY 3): tests, treatment,
# specialist, red flags, return to play. Kept in output/ai_treatment.json (no database change).
AI_TREATMENT_FILE = os.path.join(PROJECT_ROOT, "output", "ai_treatment.json")
_ai_treatment_cache = {"mtime": None, "data": {}}


def _ai_treatment_all():
    try:
        st = os.stat(AI_TREATMENT_FILE)
        mtime = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _ai_treatment_cache["mtime"] != mtime:
        try:
            with open(AI_TREATMENT_FILE, "r", encoding="utf-8") as f:
                _ai_treatment_cache["data"] = loads_maybe_encrypted(f.read())
        except Exception:          # missing, damaged or encrypted with another key: no AI results
            _ai_treatment_cache["data"] = {}
        _ai_treatment_cache["mtime"] = mtime
    return _ai_treatment_cache["data"]


def _ai_treatment_for(event_id):
    return _ai_treatment_all().get(str(event_id))


# ============================================
# SERIALIZER
# ============================================

def event_to_dict(e: InjuryEvent):

    return {
        "id": e.id,
        "player_id": e.player_id,
        "player_name": e.player.name if e.player is not None else "Unidentified",
        "jersey_number": e.player.jersey_number if e.player is not None else None,
        "team_name": (e.player.team.name if e.player is not None and e.player.team is not None else None),
        "identified": e.player_id is not None,
        "identified_at": e.identified_at,
        "identified_by": e.identified_by,
        "id_detail": e.id_detail,
        "id_confidence": e.id_confidence,
        "track_id": e.track_id,
        "video_time_sec": e.video_time_sec,
        "gemini_verdict": e.gemini_verdict,
        "gemini_confidence": e.gemini_confidence,
        "gemini_reason": e.gemini_reason,
        "gemini_description": e.gemini_description,
        "gemini_jersey": e.gemini_jersey,
        "gemini_team": e.gemini_team,
        "gemini_jersey_confidence": e.gemini_jersey_confidence,
        "gemini_checked_at": e.gemini_checked_at,
        "ai_injury": _ai_injury_for(e.id),
        "ai_treatment": _ai_treatment_for(e.id),
        "match_session_id": e.match_session_id,
        "match_name": (e.match.name if e.match is not None and e.match.name else
                       ("Match #" + str(e.match_session_id) if e.match_session_id else None)),
        "event_type": e.event_type,
        "region": e.region,
        "risk": e.risk,
        "movement": e.movement,
        "note": e.note,
        "injury_note": e.injury_note,
        "clip_url": ("/clips/" + e.clip_path) if e.clip_path else None,
        "thumb_url": ("/thumbs/" + e.clip_path + ".jpg") if e.clip_path else None,
        "source": e.source,
        "resolved": e.resolved,
        "timestamp": e.timestamp,
    }


# ============================================
# LOGIN
# ============================================

@app.post("/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Username (or registered Gmail) + password, for every role - next to Sign in with Google (POST /auth/firebase).
    Logins made for Google only have a random password nobody knows, so they cannot be used here."""

    user = _user_named(db, request.username) or _user_with_email(db, request.username)

    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    print("[AUTH]", user.username, "signed in with a password (" + user.role + ")")
    return _issue_login(user)


# ============================================
# SIGN IN WITH GOOGLE (Firebase Authentication)
# The browser signs in with Google through Firebase and sends the Firebase ID token here.
# The token is checked against Google's public keys (signature, expiry, issuer and that it
# was made for OUR Firebase project), the Gmail must be verified, and it must belong to a
# login the admin registered - that login's role is used. No password is stored or seen.
# FIREBASE_PROJECT_ID comes from .env (project root, src/.env or backend/.env).
# ============================================

class FirebaseLoginRequest(BaseModel):
    id_token: str


def _env_value(name):
    if os.environ.get(name):
        return os.environ[name].strip()
    for path in (os.path.join(PROJECT_ROOT, ".env"), os.path.join(PROJECT_ROOT, "src", ".env"), os.path.join(PROJECT_ROOT, "backend", ".env")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    k, _, v = line.strip().partition("=")
                    if k.strip() == name and v.strip():
                        return v.strip().strip('"').strip("'")
        except OSError:
            pass
    return None


def _norm_email(email):
    return (email or "").strip().lower()


def _user_with_email(db, email):
    email = _norm_email(email)
    return db.query(User).filter(User.email_lookup == lookup_hash(email)).first() if email else None


@app.post("/auth/firebase")
def firebase_login(request: FirebaseLoginRequest, db: Session = Depends(get_db)):

    project_id = _env_value("FIREBASE_PROJECT_ID")
    if not project_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not set up yet: FIREBASE_PROJECT_ID is missing in .env")

    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests

    try:
        # a token is brand new when it arrives: allow a small difference between this computer's
        # clock and Google's (a PC clock a second behind made every fresh token "used too early")
        claims = google_id_token.verify_firebase_token(request.id_token, google_requests.Request(),
                                                       audience=project_id, clock_skew_in_seconds=60)
    except Exception as e:
        reason = str(e)
        print("[AUTH] Firebase token rejected:", reason[:160])
        if "too early" in reason or "expired" in reason.lower():
            raise HTTPException(status_code=401, detail="Google sign-in failed because this computer's clock is wrong. "
                                                        "Set Windows to 'Set time automatically', then try again.")
        raise HTTPException(status_code=401, detail="Google sign-in could not be verified. Please try again.")

    if not claims or claims.get("iss") != "https://securetoken.google.com/" + project_id:
        raise HTTPException(status_code=401, detail="Google sign-in could not be verified. Please try again.")

    email = _norm_email(claims.get("email"))
    if not email or not claims.get("email_verified"):
        raise HTTPException(status_code=401, detail="This Google account has no verified email address.")

    user = _user_with_email(db, email)
    if user is None:
        print("[AUTH] Google sign-in refused for an unregistered Gmail")
        raise HTTPException(status_code=403, detail=email + " is not registered in AthleteGuard. Ask your administrator to add this Gmail.")

    print("[AUTH]", user.username, "signed in with Google (" + user.role + ")")
    return _issue_login(user)


def _issue_login(user):
    # sid -> this login's response key (secure_transport.py); the browser decrypts with session_key
    sid = secrets.token_urlsafe(18)

    token = create_access_token({
        "user_id": user.id,
        "role": user.role,
        "team_id": user.team_id,
        "sid": sid,
    })

    return {
        "access_token": token,
        "session_key": base64.b64encode(session_key(sid)).decode("ascii"),
        "role": user.role,
        "team_id": user.team_id,
        "username": user.username,
        "player_id": _player_id_of(user),
    }


# ============================================
# MATCHES
# ============================================

@app.post("/matches")
def create_match(request: MatchCreateRequest, db: Session = Depends(get_db)):

    match = MatchSession(name=request.name, video_source=request.video_source)

    db.add(match)
    db.commit()
    db.refresh(match)

    return {"message": "Match created", "match_session_id": match.id}


@app.get("/matches")
def get_matches(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    matches = db.query(MatchSession).order_by(MatchSession.id.desc()).all()     # newest first (ids grow with time)

    return [
        {
            "id": m.id,
            "name": m.name or ("Match #" + str(m.id)),
            "video_source": m.video_source,
            "date": m.date,
        }
        for m in matches
    ]


# ============================================
# EVENTS — AI SCRIPT POSTS HERE (saved even without a player)
# ============================================

@app.post("/events")
def create_event(request: EventCreateRequest, db: Session = Depends(get_db)):

    if request.player_id is not None:
        player = db.query(Player).filter(Player.id == request.player_id).first()
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")

    if request.match_session_id is not None:
        match = db.query(MatchSession).filter(MatchSession.id == request.match_session_id).first()
        if match is None:
            raise HTTPException(status_code=404, detail="Match session not found")

    event = InjuryEvent(
        player_id=request.player_id,
        match_session_id=request.match_session_id,
        event_type=_norm_code(request.event_type),
        region=_norm_code(request.region),
        risk=request.risk,
        movement=request.movement,
        injury_note=request.injury_note,
        clip_path=request.clip_path,
        source=request.source,
        track_id=request.track_id,
        video_time_sec=request.video_time_sec,
    )

    if request.player_id is not None:
        event.identified_at = now_utc()
        event.identified_by = request.identified_by
        event.id_detail = request.id_detail
        event.id_confidence = request.id_confidence

    # Same fall already saved by an earlier run of this video? The new run replaces it:
    # the old copies (rows, clips, AI results) are deleted and this event is stored.
    old_copies = _find_duplicates(db, event)

    if old_copies:
        # keep the player if this run did not identify one (e.g. picked by staff earlier)
        if event.player_id is None:
            known = next((c for c in old_copies if c.player_id is not None), None)
            if known is not None:
                event.player_id = known.player_id
                event.identified_at = known.identified_at
                event.identified_by = known.identified_by
                event.id_detail = known.id_detail
                event.id_confidence = known.id_confidence

    db.add(event)
    removed = _delete_events(db, old_copies)
    db.refresh(event)

    if removed:
        print("[EVENTS] Event", event.id, "replaces", removed, "from an earlier run of this video")
        # duplicate=True keeps the detector from sending the WhatsApp alerts again
        return {"message": "Event recorded (replaces " + ", ".join("#" + str(i) for i in removed) + ")",
                "event_id": event.id, "duplicate": True, "replaced": removed}

    return {"message": "Event recorded", "event_id": event.id, "duplicate": False}


def _delete_events(db, events):
    """Deletes the events with their clip files and AI / assessment results; commits. Returns their ids."""
    ids = [e.id for e in events]
    clips = {e.clip_path for e in events if e.clip_path}
    for e in events:
        db.delete(e)
    db.commit()
    for clip in clips:
        if not _clip_used_by_other_event(db, clip, ids):
            _remove_clip_file(clip)
    if ids:
        for path in (AI_INJURY_FILE, AI_TREATMENT_FILE, ASSESSMENTS_FILE):
            data = _load_json(path, None)
            if isinstance(data, dict) and any(str(i) in data for i in ids):
                for i in ids:
                    data.pop(str(i), None)
                _save_json(path, data)
    return ids


def _find_duplicates(db, new_event):
    """Every event from an earlier run of the same video that is the same fall as new_event."""

    if new_event.match_session_id is None or new_event.video_time_sec is None:
        return []
    if (new_event.source or "ai") != "ai":
        return []

    match = db.query(MatchSession).filter(MatchSession.id == new_event.match_session_id).first()
    key = _video_key(match)

    if key is None:
        return []

    # match and video time are encrypted: checked in Python
    candidates = [
        c for c in (
            db.query(InjuryEvent)
            .filter(InjuryEvent.match_session_id.isnot(None), InjuryEvent.video_time_sec.isnot(None))
            .all()
        )
        if c.match_session_id != new_event.match_session_id
        and abs(c.video_time_sec - new_event.video_time_sec) <= DUPLICATE_WINDOW_SEC
        and c.match is not None
    ]

    return [c for c in candidates if _same_fall(new_event, c, key_a=key)]


# ============================================
# EVENTS — AI SCRIPT FILLS IN PLAYER / CLIP LATER
# ============================================

@app.patch("/events/{event_id}/ai-update")
def ai_update_event(event_id: int, request: EventAIUpdateRequest, db: Session = Depends(get_db)):

    event = db.query(InjuryEvent).filter(InjuryEvent.id == event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if request.player_id is not None:

        player = db.query(Player).filter(Player.id == request.player_id).first()

        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")

        # never overwrite a staff decision, and only replace a Gemini answer with a surer one
        keep_existing = (
            event.player_id is not None
            and (
                event.identified_by == "manual"
                or (
                    event.identified_by == "gemini"
                    and (request.id_confidence or 0) <= (event.id_confidence or 0)
                )
            )
        )

        if not keep_existing:
            event.player_id = request.player_id
            event.identified_at = now_utc()
            event.identified_by = request.identified_by
            event.id_detail = request.id_detail
            event.id_confidence = request.id_confidence

    if request.clip_path is not None:
        # A re-run of the same video sends a second clip for the same fall:
        # keep the clip that already works. The new file is NOT deleted, because
        # another (new) event from the same frame may be using it.
        if not (event.clip_path and event.clip_path != request.clip_path and _clip_exists(event.clip_path)):
            event.clip_path = request.clip_path

    if request.injury_note is not None:
        event.injury_note = request.injury_note

    db.commit()
    db.refresh(event)

    return {"message": "Event updated", "event": event_to_dict(event)}


# ============================================
# EVENTS — GEMINI SECOND OPINION (sent by src/gemini_verifier.py and src/verify_clips.py)
# - confident false alarm  -> event and its clip are deleted
#   (?keep_false_alarm=true only stores the verdict, the dashboard then shows it)
# - confident jersey read  -> replaces our player if Gemini is surer
#   (?min_jersey_confidence=0.85 asks for a stricter jersey rule than the default)
# ============================================

@app.patch("/events/{event_id}/gemini")
def gemini_result(
    event_id: int,
    request: GeminiResultRequest,
    keep_false_alarm: bool = Query(False),
    min_jersey_confidence: Optional[float] = Query(None),
    jersey_only: bool = Query(False),
    db: Session = Depends(get_db)
):

    event = db.query(InjuryEvent).filter(InjuryEvent.id == event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    verdict = (request.verdict or "unsure").lower()
    confidence = request.confidence if request.confidence is not None else 0.0
    jersey_min = max(GEMINI_JERSEY_MIN_CONFIDENCE, min_jersey_confidence or 0.0)

    # 1) confident false alarm -> delete (never in jersey-only mode: the injury check decides that)
    if (not jersey_only and verdict == "false_alarm" and confidence >= _gemini_delete_min()
            and event.identified_by != "manual" and not keep_false_alarm):

        clip_path = event.clip_path
        shared = _clip_used_by_other_event(db, clip_path, [event.id])

        db.delete(event)
        db.commit()

        if clip_path and not shared:
            _remove_clip_file(clip_path)

        return {"action": "deleted", "event_id": event_id, "reason": request.reason}

    # 2) store the second opinion (jersey-only: just the shirt read, no fall verdict)
    if not jersey_only:
        event.gemini_verdict = verdict
        event.gemini_confidence = request.confidence
        event.gemini_reason = request.reason
        event.gemini_description = request.description
    event.gemini_team = request.team
    event.gemini_jersey = request.jersey_number
    event.gemini_jersey_confidence = request.jersey_confidence
    event.gemini_checked_at = now_utc()

    action = "stored"

    # 3) Gemini's jersey read -> player, if it is surer than ours
    jersey_conf = request.jersey_confidence or 0.0

    if (
        request.jersey_number is not None
        and request.team
        and request.team.lower() != "unknown"
        and jersey_conf >= jersey_min
        and event.identified_by != "manual"
    ):

        team = _team_named(db, request.team)
        player = next(
            (p for p in _players_of_team(db, team.id) if p.jersey_number == request.jersey_number),
            None,
        ) if team is not None else None

        if player is not None and player.id != event.player_id:

            ours = event.id_confidence or 0.0

            if event.player_id is None or jersey_conf > ours:

                previous = (
                    event.player.name + " (" + str(round(ours * 100)) + "%)"
                    if event.player is not None else "Unidentified"
                )

                event.player_id = player.id
                event.identified_at = now_utc()
                event.identified_by = "gemini"
                event.id_detail = (
                    "Gemini read #" + str(request.jersey_number) + " (" + player.team.name + ")"
                    + " - model said: " + previous
                )
                event.id_confidence = jersey_conf

                action = "reassigned" if previous != "Unidentified" else "identified"

    db.commit()
    db.refresh(event)

    return {"action": action, "event": event_to_dict(event)}


# ============================================
# EVENTS — GEMINI INJURY CHECK (sent by src/gemini_injury.py)
# Stores the possible injuries (names, risk, safety measure and rest time come from
# src/injury_catalog.py) in output/ai_injury.json. Removing a fall that was not an
# injury goes through PATCH /events/{id}/gemini like the other false alarms.
# ============================================

AI_INJURY_RISKS = ("Low", "Low-Medium", "Medium", "Medium-High", "High", "Critical")


class AiInjuryItem(BaseModel):
    injury: str
    body_area: str
    risk: str
    safety_measure: str
    rest: str
    likelihood: Optional[float] = None


class AiInjuryRequest(BaseModel):
    injury_event: bool = True
    confidence: Optional[float] = None
    action: Optional[str] = None
    description: Optional[str] = None
    side: Optional[str] = None
    injuries: list[AiInjuryItem] = []
    rest: Optional[str] = None
    risk: Optional[str] = None
    model: Optional[str] = None


def _clip_text(v, n):
    v = str(v or "").strip()
    return v[:n] or None


@app.patch("/events/{event_id}/ai-injury")
def ai_injury_result(event_id: int, request: AiInjuryRequest, db: Session = Depends(get_db)):

    event = db.query(InjuryEvent).filter(InjuryEvent.id == event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    injuries = []
    for i in request.injuries[:5]:
        injuries.append({
            "injury": _clip_text(i.injury, 80),
            "body_area": _clip_text(i.body_area, 40),
            "risk": i.risk if i.risk in AI_INJURY_RISKS else None,
            "safety_measure": _clip_text(i.safety_measure, 160),
            "rest": _clip_text(i.rest, 40),
            "likelihood": max(0.0, min(1.0, i.likelihood)) if i.likelihood is not None else None,
        })

    if not injuries:
        raise HTTPException(status_code=400, detail="At least one possible injury is required")

    record = {
        "injury_event": bool(request.injury_event),
        "confidence": request.confidence,
        "action": _clip_text(request.action, 120),
        "description": _clip_text(request.description, 300),
        "side": request.side if request.side in ("left", "right") else None,
        "injuries": injuries,
        "rest": _clip_text(request.rest, 40) or injuries[0]["rest"],
        "risk": request.risk if request.risk in AI_INJURY_RISKS else None,
        "model": _clip_text(request.model, 60),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    data = dict(_load_json(AI_INJURY_FILE, {}))
    data[str(event_id)] = record
    _save_json(AI_INJURY_FILE, data)

    print("[INJURY-AI] event", event_id, "->", ", ".join(i["injury"] for i in injuries), "| rest", record["rest"])

    return {"action": "stored", "event": event_to_dict(event)}


# ============================================
# EVENTS — MEDICAL RECOMMENDATION (sent by src/gemini_treatment.py, KEY 3)
# Detailed review of the clip: mechanism, likely injuries, on-field safety measures,
# recommended tests (CT / MRI / X-ray ...), treatment, specialist, red flags and return
# to play. Stored in output/ai_treatment.json. Never deletes anything.
# ============================================

AI_TREATMENT_SEVERITIES = ("Low", "Medium", "High", "Critical")
AI_TREATMENT_URGENCIES = ("Emergency", "Same day", "Within 48 hours", "Routine")


class AiTreatmentInjury(BaseModel):
    injury: str
    likelihood: Optional[float] = None
    why: Optional[str] = None


class AiTreatmentTest(BaseModel):
    test: str
    why: Optional[str] = None


class AiTreatmentRequest(BaseModel):
    mechanism: Optional[str] = None
    body_part: Optional[str] = None
    side: Optional[str] = None
    severity: Optional[str] = None
    urgency: Optional[str] = None
    confidence: Optional[float] = None
    injuries: list[AiTreatmentInjury] = []
    on_field: list[str] = []
    tests: list[AiTreatmentTest] = []
    treatment: list[str] = []
    specialist: Optional[str] = None
    red_flags: list[str] = []
    return_to_play: Optional[str] = None
    model: Optional[str] = None


def _clip_list(items, n_items, n_chars):
    return [t for t in (_clip_text(i, n_chars) for i in (items or [])[:n_items]) if t]


@app.patch("/events/{event_id}/ai-treatment")
def ai_treatment_result(event_id: int, request: AiTreatmentRequest, db: Session = Depends(get_db)):

    event = db.query(InjuryEvent).filter(InjuryEvent.id == event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    record = {
        "mechanism": _clip_text(request.mechanism, 400),
        "body_part": _clip_text(request.body_part, 60),
        "side": request.side if request.side in ("left", "right") else None,
        "severity": request.severity if request.severity in AI_TREATMENT_SEVERITIES else None,
        "urgency": request.urgency if request.urgency in AI_TREATMENT_URGENCIES else None,
        "confidence": max(0.0, min(1.0, request.confidence)) if request.confidence is not None else None,
        "injuries": [
            {"injury": _clip_text(i.injury, 80),
             "likelihood": max(0.0, min(1.0, i.likelihood)) if i.likelihood is not None else None,
             "why": _clip_text(i.why, 200)}
            for i in request.injuries[:3] if _clip_text(i.injury, 80)
        ],
        "on_field": _clip_list(request.on_field, 6, 160),
        "tests": [{"test": _clip_text(t.test, 100), "why": _clip_text(t.why, 200)}
                  for t in request.tests[:5] if _clip_text(t.test, 100)],
        "treatment": _clip_list(request.treatment, 6, 160),
        "specialist": _clip_text(request.specialist, 120),
        "red_flags": _clip_list(request.red_flags, 5, 120),
        "return_to_play": _clip_text(request.return_to_play, 200),
        "model": _clip_text(request.model, 60),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    if not (record["injuries"] or record["tests"] or record["on_field"]):
        raise HTTPException(status_code=400, detail="Nothing to store")

    data = dict(_load_json(AI_TREATMENT_FILE, {}))
    data[str(event_id)] = record
    _save_json(AI_TREATMENT_FILE, data)

    print("[TREATMENT-AI] event", event_id, "->", record["severity"], "/", record["urgency"],
          "| tests:", ", ".join(t["test"] for t in record["tests"]) or "-")

    return {"action": "stored", "event": event_to_dict(event)}


# ============================================
# EVENTS — ASSIGN / CORRECT THE PLAYER
# Used from the dashboard after watching the clip.
# - Unidentified event: ANY logged-in user (admin, medical, coach)
#   can pick the player.
# - Already identified event: only medical staff or admin can change it.
# The AI never overwrites a manual choice (see /ai-update and /gemini).
# ============================================

@app.patch("/events/{event_id}/assign")
def assign_player(
    event_id: int,
    request: AssignPlayerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    event = db.query(InjuryEvent).filter(InjuryEvent.id == event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    is_staff = current_user.role in ("medical", "admin")

    if not is_staff:

        if current_user.role not in ("coach", "owner"):
            raise HTTPException(status_code=403, detail="Unknown role")

        if event.player_id is not None:
            current = event.player.name if event.player is not None else "a player"
            raise HTTPException(
                status_code=409,
                detail="Already identified as " + current + ". Only medical staff or admin can change it."
            )

    player = db.query(Player).filter(Player.id == request.player_id).first()

    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    previous = event.player.name if event.player is not None else "Unidentified"

    event.player_id = player.id
    event.identified_at = now_utc()
    event.identified_by = "manual"
    event.id_detail = (
        "chosen from clip by " + current_user.username + " (" + current_user.role + ")"
        + " - was: " + previous
    )
    event.id_confidence = None

    db.commit()
    db.refresh(event)

    return {"message": "Player assigned", "event": event_to_dict(event)}


# ============================================
# EVENTS — MEDICAL STAFF MANUAL LOGGING
# ============================================

@app.post("/events/manual")
def create_manual_event(
    request: ManualEventRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    if current_user.role != "medical":
        raise HTTPException(status_code=403, detail="Only medical staff can log manual events")

    player = db.query(Player).filter(Player.id == request.player_id).first()

    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    event = InjuryEvent(
        player_id=request.player_id,
        match_session_id=request.match_session_id,
        event_type=_norm_code(request.event_type),
        note=request.note,
        risk=request.risk,
        source="manual",
        identified_by="manual",
        id_detail="logged by " + current_user.username,
    )

    event.identified_at = now_utc()

    db.add(event)
    db.commit()
    db.refresh(event)

    return {"message": "Manual event recorded", "event_id": event.id}


# ============================================
# GET EVENTS — medical/admin: all. coach: own team + Unidentified
# ============================================

@app.get("/events")
def get_events(
    match_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    if current_user.role not in ("medical", "admin", "coach", "owner", "player"):
        raise HTTPException(status_code=403, detail="Unknown role")

    # player / team / match links are encrypted: visibility and the match filter run in Python
    # (coach / owner: own team's events + every Unidentified fall; player: only their own falls)
    events = [
        e for e in db.query(InjuryEvent).order_by(InjuryEvent.id.desc()).all()     # newest first (ids grow with time)
        if _can_see_event(current_user, e) and (match_id is None or e.match_session_id == match_id)
    ]

    return [event_to_dict(e) for e in events]
    # ============================================
# GET PLAYERS — all players, both teams, for every role
# ============================================

# Every role gets BOTH teams: an Unidentified fall can be any player,
# so coaches need the full roster to pick from when reviewing a clip.

@app.get("/players")
def get_players(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    query = db.query(Player)

    # a player only gets their own record
    if current_user.role == "player":
        query = query.filter(Player.id == (_player_id_of(current_user) or -1))

    players = query.all()

    # a team owner only gets their own team's players (no details of the other team)
    if current_user.role == "owner":
        players = [p for p in players if p.team_id == current_user.team_id]

    players.sort(key=lambda p: (p.team_id, p.jersey_number))

    return [
        {
            "id": p.id,
            "name": p.name,
            "jersey_number": p.jersey_number,
            "team_id": p.team_id,
            "team_name": p.team.name if p.team is not None else None,
        }
        for p in players
    ]


# ============================================
# GET TEAMS — admin/medical: both teams. coach: own team only.
# ============================================

@app.get("/teams")
def get_teams(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    if current_user.role in ("medical", "admin"):
        teams = db.query(Team).order_by(Team.id).all()

    elif current_user.role in ("coach", "player", "owner"):
        teams = db.query(Team).filter(Team.id == current_user.team_id).all()

    else:
        raise HTTPException(status_code=403, detail="Unknown role")

    result = []

    # risk is encrypted: count per player in Python (one pass over the identified events)
    total_by_player, high_by_player = {}, {}
    for e in db.query(InjuryEvent).filter(InjuryEvent.player_id.isnot(None)).all():
        total_by_player[e.player_id] = total_by_player.get(e.player_id, 0) + 1
        if e.risk == "HIGH":
            high_by_player[e.player_id] = high_by_player.get(e.player_id, 0) + 1

    all_users = db.query(User).all()

    for t in teams:

        players = sorted(_players_of_team(db, t.id), key=lambda p: p.jersey_number)

        coaches = [u for u in all_users if u.role == "coach" and u.team_id == t.id]

        rows = []
        team_total = 0
        team_high = 0

        for p in players:

            total = total_by_player.get(p.id, 0)
            high = high_by_player.get(p.id, 0)

            team_total += total
            team_high += high

            rows.append({
                "id": p.id,
                "name": p.name,
                "jersey_number": p.jersey_number,
                "injury_events": total,
                "high_risk_events": high,
            })

        result.append({
            "id": t.id,
            "name": t.name,
            "coaches": [c.username for c in coaches],
            "player_count": len(rows),
            "injury_events": team_total,
            "high_risk_events": team_high,
            "players": rows,
        })

    return result


# ============================================
# ADMIN — TEAMS AND PLAYERS (create team, register / edit player)
# The detector loads the roster when it starts, so new players are used from the next run.
# ============================================

def _require_roster_admin(user):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the admin can add or change teams and players")


class TeamCreateRequest(BaseModel):
    name: str


class PlayerRequest(BaseModel):
    name: str
    jersey_number: int
    team_id: int


def _check_player_fields(db, request, player_id=None):
    name = " ".join((request.name or "").split())
    if not name or len(name) > 80:
        raise HTTPException(status_code=400, detail="Player name is required (80 characters at most)")
    if not 1 <= int(request.jersey_number) <= 99:
        raise HTTPException(status_code=400, detail="Jersey number must be between 1 and 99")
    if db.query(Team).filter(Team.id == request.team_id).first() is None:
        raise HTTPException(status_code=404, detail="Team not found")
    clash = next((p for p in _players_of_team(db, request.team_id)
                  if p.jersey_number == request.jersey_number and p.id != player_id), None)
    if clash is not None:
        raise HTTPException(status_code=409, detail="#" + str(request.jersey_number) + " is already " + clash.name + " in this team")
    return name


def _player_out(p):
    return {"id": p.id, "name": p.name, "jersey_number": p.jersey_number, "team_id": p.team_id,
            "team_name": p.team.name if p.team is not None else None}


@app.post("/teams")
def create_team(request: TeamCreateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_roster_admin(current_user)
    name = " ".join((request.name or "").split())
    if not name or len(name) > 60:
        raise HTTPException(status_code=400, detail="Team name is required (60 characters at most)")
    if _team_named(db, name) is not None:
        raise HTTPException(status_code=409, detail="A team called " + name + " already exists")
    team = Team(name=name)
    db.add(team)
    db.commit()
    db.refresh(team)
    print("[TEAMS]", current_user.username, "created team", name)
    return {"id": team.id, "name": team.name}


@app.post("/players")
def create_player(request: PlayerRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_roster_admin(current_user)
    name = _check_player_fields(db, request)
    player = Player(name=name, jersey_number=request.jersey_number, team_id=request.team_id)
    db.add(player)
    db.commit()
    db.refresh(player)
    print("[PLAYERS]", current_user.username, "registered", name, "#" + str(request.jersey_number))
    return _player_out(player)


@app.put("/players/{player_id}")
def update_player(player_id: int, request: PlayerRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_roster_admin(current_user)
    player = db.query(Player).filter(Player.id == player_id).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    player.name = _check_player_fields(db, request, player_id)
    player.jersey_number = request.jersey_number
    player.team_id = request.team_id
    db.commit()
    db.refresh(player)
    return _player_out(player)


# ============================================
# ADMIN — DELETE ONE EVENT (e.g. a test or wrong detection)
# Removes the event, its clip (unless another event uses it) and its
# AI results / medical assessment from the JSON stores.
# ============================================

@app.delete("/events/{event_id}")
def delete_event(event_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete an event")

    event = db.query(InjuryEvent).filter(InjuryEvent.id == event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    _delete_events(db, [event])

    print("[EVENTS]", current_user.username, "deleted event", event_id)

    return {"message": "Event #" + str(event_id) + " deleted", "event_id": event_id}


# ============================================
# MARK EVENT RESOLVED
# ============================================

@app.patch("/events/{event_id}/resolve")
def resolve_event(event_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    if current_user.role == "player":
        raise HTTPException(status_code=403, detail="Players cannot change the review state")

    event = db.query(InjuryEvent).filter(InjuryEvent.id == event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    event.resolved = True
    db.commit()

    return {"message": "Event marked as resolved"}


# ============================================
# ADMIN — REMOVE DUPLICATE EVENTS
# Also runs automatically every time the backend starts.
# ?dry_run=true only lists what would be removed.
# ============================================

@app.post("/admin/events/remove-duplicates")
def admin_remove_duplicates(
    dry_run: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can perform this action")

    report = remove_duplicate_events(db, dry_run=dry_run)

    return {
        "dry_run": dry_run,
        "groups": report,
        "removed_events": sum(len(r["removed"]) for r in report),
    }


# ============================================
# ADMIN — CLEAR ALL INJURY EVENTS (players are kept)
# ============================================

@app.delete("/admin/players/clear")
def clear_all_injury_events(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can perform this action")

    deleted = db.query(InjuryEvent).delete()
    db.commit()

    return {"message": "All injury events deleted. Players were kept.", "deleted_events": deleted}


# ============================================
# ADMIN — USER ACCOUNTS (Users page in the dashboard)
# The admin creates a login: username (plain text like "coach3"),
# a starting password and a role. A coach must be linked to a team
# because coaches only see their own team's events.
# Passwords are stored hashed, exactly the way /auth/login checks them.
# ============================================

USER_ROLES = ("admin", "medical", "coach", "player", "owner")

# A team owner manages their own team's logins: creates and removes coach and player
# accounts of that team. Medical, admin and owner accounts can only be removed by the admin.
OWNER_CAN_CREATE = ("coach", "player")
OWNER_CAN_REMOVE = ("coach", "player")

# Player logins: which roster player each "player" account belongs to.
# Kept in output/player_accounts.json ({"<user id>": <player id>}), so the database is not changed.
PLAYER_ACCOUNTS_FILE = os.path.join(PROJECT_ROOT, "output", "player_accounts.json")


def _player_accounts():
    data = _load_json(PLAYER_ACCOUNTS_FILE, {})
    return data if isinstance(data, dict) else {}


def _player_id_of(user):
    """Roster player id of a player login, else None."""
    if user is None or user.role != "player":
        return None
    try:
        value = _player_accounts().get(str(user.id))
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 72      # bcrypt only uses the first 72 bytes


class UserCreateRequest(BaseModel):
    username: Optional[str] = None    # defaults to the Gmail
    password: Optional[str] = None    # admin logins only (emergency login); others sign in with Google
    email: Optional[str] = None       # Gmail for "Sign in with Google" - required for every role except admin
    role: str                         # admin / medical / coach / player / owner
    team_id: Optional[int] = None     # required for coach and owner, ignored otherwise
    player_id: Optional[int] = None   # required for player: the roster player this login belongs to


def user_to_dict(u: User):

    out = {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "role": u.role,
        "team_id": u.team_id,
        "team_name": u.team.name if u.team is not None else None,
        "player_id": None,
        "player_name": None,
        "jersey_number": None,
        "coaches": [],
    }

    pid = _player_id_of(u)
    session = object_session(u)

    if pid is not None and session is not None:
        player = session.query(Player).filter(Player.id == pid).first()
        if player is not None:
            out["player_id"] = player.id
            out["player_name"] = player.name
            out["jersey_number"] = player.jersey_number
            out["coaches"] = [c.username for c in session.query(User).all() if c.role == "coach" and c.team_id == player.team_id]

    return out


def _require_admin(current_user: User):

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can manage user accounts")


def _require_admin_or_owner(current_user: User):

    if current_user.role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Only admin or the team owner can manage user accounts")


@app.get("/admin/users")
def list_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    _require_admin_or_owner(current_user)

    users = db.query(User).all()

    # team owner: their own team's logins + medical staff (view only); never the other team
    if current_user.role == "owner":
        users = [u for u in users if u.team_id == current_user.team_id or u.role == "medical"]

    users.sort(key=lambda u: (u.role, u.username.lower()))

    return [user_to_dict(u) for u in users]


@app.post("/admin/users")
def create_user(
    request: UserCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    _require_admin_or_owner(current_user)

    role = (request.role or "").strip().lower()
    email = _check_email(db, request.email) if (request.email or "").strip() else None
    username = (request.username or "").strip() or (email or "")
    password = request.password or ""

    if role not in USER_ROLES:
        raise HTTPException(status_code=400, detail="Role must be admin, medical, coach, player or owner")

    # everyone signs in with Google except the admin, who keeps a password as the emergency way in
    if role != "admin" and not email:
        raise HTTPException(status_code=400, detail="Enter the Gmail this person signs in with")

    if role == "admin" or password:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(status_code=400, detail="Password must be at least " + str(MIN_PASSWORD_LENGTH) + " characters")
        if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
            raise HTTPException(status_code=400, detail="Password must be " + str(MAX_PASSWORD_LENGTH) + " characters or fewer")
    else:
        password = secrets.token_urlsafe(32)     # never used: this login only works with Google

    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    if any(ch.isspace() for ch in username):
        raise HTTPException(status_code=400, detail="Username cannot contain spaces")

    if len(username) > 80:
        raise HTTPException(status_code=400, detail="Username must be 80 characters or fewer")

    is_owner = current_user.role == "owner"

    if is_owner and role not in OWNER_CAN_CREATE:
        raise HTTPException(status_code=403, detail="A team owner can only create coach and player logins")

    taken = _user_named(db, username)       # case-insensitive (lookup hash of the lower-case name)

    if taken is not None:
        raise HTTPException(status_code=409, detail="Username '" + username + "' is already taken")

    team_id = None

    if role in ("coach", "owner"):

        # a team owner always creates logins for their own team
        wanted_team = current_user.team_id if is_owner else request.team_id

        if wanted_team is None:
            raise HTTPException(status_code=400, detail="Pick the team this " + ("owner" if role == "owner" else "coach") + " belongs to")

        team = db.query(Team).filter(Team.id == wanted_team).first()

        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")

        team_id = team.id

    player = None

    if role == "player":

        if request.player_id is None:
            raise HTTPException(status_code=400, detail="Pick the player this login belongs to")

        player = db.query(Player).filter(Player.id == request.player_id).first()

        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")

        if is_owner and player.team_id != current_user.team_id:
            raise HTTPException(status_code=403, detail="A team owner can only create logins for their own team's players")

        accounts = _player_accounts()
        existing_ids = [int(k) for k, v in accounts.items() if str(k).isdigit() and v == player.id]
        if existing_ids and db.query(User).filter(User.id.in_(existing_ids)).first() is not None:
            raise HTTPException(status_code=409, detail=player.name + " already has a player login")

        team_id = player.team_id

    user = User(
        username=username,
        password_hash=pwd_context.hash(password),
        role=role,
        team_id=team_id,
    )
    user.set_email(email)

    db.add(user)
    db.commit()
    db.refresh(user)

    if player is not None:
        accounts = _player_accounts()
        accounts[str(user.id)] = player.id
        _save_json(PLAYER_ACCOUNTS_FILE, accounts)

    print("[USERS]", current_user.username, "created", username, "(" + role + ")")

    return {"message": "User created", "user": user_to_dict(user)}


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _check_email(db, email, user_id=None):
    """Lower-case Gmail (or other Google account); must be free (not on another login)."""
    email = _norm_email(email)
    if not EMAIL_PATTERN.match(email) or len(email) > 120:
        raise HTTPException(status_code=400, detail="Enter a valid Gmail address, e.g. name@gmail.com")
    other = _user_with_email(db, email)
    if other is not None and other.id != user_id:
        raise HTTPException(status_code=409, detail=email + " is already used by the login " + other.username)
    return email


class UserEmailRequest(BaseModel):
    email: Optional[str] = None       # empty = remove the Gmail (Google sign-in off for this login)


@app.put("/admin/users/{user_id}/email")
def set_user_email(user_id: int, request: UserEmailRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Assign (or change) the Gmail a login signs in with."""
    _require_admin_or_owner(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if current_user.role == "owner" and (user.role not in OWNER_CAN_REMOVE or user.team_id != current_user.team_id):
        raise HTTPException(status_code=403, detail="A team owner can only change their own team's coach and player logins")
    email = _check_email(db, request.email, user.id) if (request.email or "").strip() else None
    if email is None and user.role != "admin":
        raise HTTPException(status_code=400, detail="Enter the Gmail this person signs in with")
    user.set_email(email)
    db.commit()
    print("[USERS]", current_user.username, "set the Gmail of", user.username)
    return {"message": "Gmail saved", "user": user_to_dict(user)}


class PasswordResetRequest(BaseModel):
    new_password: str


@app.put("/admin/users/{user_id}/password")
def reset_user_password(user_id: int, request: PasswordResetRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """'Forgot password': the admin (or a team owner, for their own coach / player logins) sets a new one."""
    _require_admin_or_owner(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if current_user.role == "owner" and (user.role not in OWNER_CAN_REMOVE or user.team_id != current_user.team_id):
        raise HTTPException(status_code=403, detail="A team owner can only reset their own team's coach and player logins")
    new = request.new_password or ""
    if len(new) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail="Password must be at least " + str(MIN_PASSWORD_LENGTH) + " characters")
    if len(new.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail="Password must be " + str(MAX_PASSWORD_LENGTH) + " characters or fewer")
    user.password_hash = pwd_context.hash(new)
    db.commit()
    print("[USERS]", current_user.username, "reset the password of", user.username)
    return {"message": "Password reset for " + user.username}


@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    _require_admin_or_owner(current_user)

    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    # team owner: only coach and player logins of their own team (never medical, admin or owner)
    if current_user.role == "owner":
        if user.role not in OWNER_CAN_REMOVE:
            raise HTTPException(status_code=403, detail="A team owner cannot remove " + user.role + " accounts")
        if user.team_id != current_user.team_id:
            raise HTTPException(status_code=403, detail="A team owner can only remove their own team's logins")

    if user.role == "admin" and sum(1 for u in db.query(User).all() if u.role == "admin") <= 1:
        raise HTTPException(status_code=400, detail="At least one admin account must remain")

    username = user.username

    db.delete(user)
    db.commit()

    accounts = _player_accounts()
    if str(user_id) in accounts:
        accounts.pop(str(user_id), None)
        _save_json(PLAYER_ACCOUNTS_FILE, accounts)

    print("[USERS]", current_user.username, "deleted", username)

    return {"message": "User " + username + " deleted", "deleted_user_id": user_id}


# ============================================
# SYSTEM STATUS (System page in the dashboard)
# The detector (src/system_status.py) reports what it is using when it starts,
# sends a heartbeat every few seconds while it runs, and reports again when it
# finishes. The report is kept in output/detector_status.json (no database change).
# GET /admin/system combines that report with live checks of the backend,
# the database and the medical knowledge base (src/injury_notes.py).
# ============================================

import json
import platform
import importlib.util
from datetime import datetime, timezone

DETECTOR_STATUS_FILE = os.path.join(PROJECT_ROOT, "output", "detector_status.json")
INJURY_NOTES_FILE = os.path.join(PROJECT_ROOT, "src", "injury_notes.py")
HEARTBEAT_STALE_SECONDS = 30      # no heartbeat for this long while "running" = stopped unexpectedly


class DetectorStatusRequest(BaseModel):
    state: str                                  # starting / running / finished
    info: dict = {}                             # model, tracker, OCR, versions... (sent at start)
    progress: dict = {}                         # frame, total_frames, events... (sent with every heartbeat)


def _now_utc():
    return datetime.now(timezone.utc)


def _read_detector_status():
    return _load_json(DETECTOR_STATUS_FILE, None)


@app.post("/system/detector-status")
def report_detector_status(request: DetectorStatusRequest):

    state = (request.state or "").strip().lower()

    if state not in ("starting", "running", "finished"):
        raise HTTPException(status_code=400, detail="state must be starting, running or finished")

    current = _read_detector_status() or {}

    # a new run starts fresh; heartbeats only update progress
    if state == "starting":
        current = {"info": request.info or {}, "started_at": _now_utc().isoformat()}
    elif request.info:
        current.setdefault("info", {}).update(request.info)

    current["state"] = state
    current["progress"] = request.progress or current.get("progress", {})
    current["last_seen"] = _now_utc().isoformat()

    if state == "finished":
        current["finished_at"] = current["last_seen"]

    _save_json(DETECTOR_STATUS_FILE, current)

    return {"message": "Status saved", "state": state}


def _medical_knowledge_base():

    if not os.path.isfile(INJURY_NOTES_FILE):
        return {"ok": False, "detail": "src/injury_notes.py not found"}

    try:
        spec = importlib.util.spec_from_file_location("injury_notes_status_check", INJURY_NOTES_FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        notes = getattr(module, "NOTES", {}) or {}
        measures = getattr(module, "SAFETY_MEASURES", {}) or {}

        note_count = sum(len(v) for v in notes.values())
        measure_sets = sum(len(v) for v in measures.values())
        measure_steps = sum(len(steps) for v in measures.values() for steps in v.values())

        return {
            "ok": note_count > 0,
            "risk_levels": sorted(notes.keys()),
            "injury_notes": note_count,
            "safety_measure_sets": measure_sets,
            "safety_measure_steps": measure_steps,
            "has_collision_rules": hasattr(module, "COLLISION_MEASURES"),
        }

    except Exception as e:
        return {"ok": False, "detail": "injury_notes.py could not be loaded: " + str(e)}


@app.get("/admin/system")
def system_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    _require_admin_or_owner(current_user)    # owner: read-only view

    now = _now_utc()

    # ---- database (the query itself proves it is reachable) ----
    try:
        db.execute(text("SELECT 1"))
        database = {
            "ok": True,
            "engine": db.get_bind().dialect.name,
            "users": db.query(func.count(User.id)).scalar() or 0,
            "teams": db.query(func.count(Team.id)).scalar() or 0,
            "players": db.query(func.count(Player.id)).scalar() or 0,
            "matches": db.query(func.count(MatchSession.id)).scalar() or 0,
            "events": db.query(func.count(InjuryEvent.id)).scalar() or 0,
        }
    except Exception as e:
        database = {"ok": False, "detail": str(e)}

    # ---- identification results so far ----
    identity = {}
    try:
        total = db.query(func.count(InjuryEvent.id)).scalar() or 0
        identified = db.query(func.count(InjuryEvent.id)).filter(InjuryEvent.player_id.isnot(None)).scalar() or 0
        by_method = {}
        for e in db.query(InjuryEvent).filter(InjuryEvent.player_id.isnot(None)).all():
            by_method[e.identified_by] = by_method.get(e.identified_by, 0) + 1
        by_method = list(by_method.items())
        gemini_checked = db.query(func.count(InjuryEvent.id)).filter(InjuryEvent.gemini_verdict.isnot(None)).scalar() or 0
        identity = {
            "events": total,
            "identified": identified,
            "unidentified": total - identified,
            "by_method": {(m or "unknown"): c for m, c in by_method},
            "gemini_checked": gemini_checked,
        }
    except Exception as e:
        identity = {"detail": str(e)}

    # ---- last job ----
    last_job = None
    try:
        m = db.query(MatchSession).order_by(MatchSession.id.desc()).first()
        if m is not None:
            match_events = _events_of_match(db, m.id)
            ev_count = len(match_events)
            ev_ident = sum(1 for e in match_events if e.player_id is not None)
            last_job = {
                "id": m.id,
                "name": m.name or ("Match #" + str(m.id)),
                "video_source": m.video_source,
                "date": m.date,
                "events": ev_count,
                "identified": ev_ident,
            }
    except Exception:
        last_job = None

    # ---- detector (from its last report) ----
    detector = _read_detector_status()

    if detector is None:
        detector = {"state": "never", "info": {}, "progress": {}}
    else:
        seconds_ago = None
        try:
            seconds_ago = (now - datetime.fromisoformat(detector.get("last_seen"))).total_seconds()
        except (TypeError, ValueError):
            pass
        detector["seconds_since_last_signal"] = round(seconds_ago) if seconds_ago is not None else None
        if detector.get("state") in ("starting", "running") and (seconds_ago is None or seconds_ago > HEARTBEAT_STALE_SECONDS):
            detector["state"] = "stopped"          # closed or crashed without saying "finished"

    return {
        "checked_at": now.isoformat(),
        "backend": {
            "ok": True,
            "python": platform.python_version(),
            "heartbeat_timeout_seconds": HEARTBEAT_STALE_SECONDS,
        },
        "database": database,
        "detector": detector,
        "identity": identity,
        "medical_knowledge_base": _medical_knowledge_base(),
        "last_job": last_job,
    }


# ============================================
# STAFF FEATURES (medical staff and coach dashboards)
# Everything here is kept in small JSON files in the output folder,
# so the database schema is not changed:
#   output/assessments.json  - medical assessment per event
#   output/alert_reads.json  - which alerts each user has read
# Player reference photos go to known_players/<jersey> - <name>/,
# the same folder the detector reads faces from.
# ============================================

import base64
import re
import unicodedata
from fastapi.responses import FileResponse

ASSESSMENTS_FILE = os.path.join(PROJECT_ROOT, "output", "assessments.json")
ALERT_READS_FILE = os.path.join(PROJECT_ROOT, "output", "alert_reads.json")
KNOWN_PLAYERS_DIR = os.path.join(PROJECT_ROOT, "known_players")
AUTO_FACES_DIR = os.path.join(PROJECT_ROOT, "known_players_auto")

ASSESSMENT_STATUSES = ("Under observation", "Further evaluation", "Imaging referred", "Cleared", "Referred")
ASSESSMENT_KEEPS_OPEN = ("Under observation",)      # every other status marks the event as reviewed
PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_READS_PER_USER = 5000


def _load_json(path, default):
    """Every JSON store in output/ is encrypted (crypto_store.py); older plain files still load."""
    return _crypto_load_json(path, default)


def _save_json(path, data):
    try:
        _crypto_save_json(path, data)
    except OSError as e:
        raise HTTPException(status_code=500, detail="Could not save: " + str(e))


def _can_see_event(user: User, event: InjuryEvent):
    """Medical/admin see every event. A coach sees their team's events and every Unidentified fall."""
    if user.role in ("medical", "admin"):
        return True
    if user.role in ("coach", "owner"):
        return event.player is None or event.player.team_id == user.team_id
    if user.role == "player":
        pid = _player_id_of(user)
        return pid is not None and event.player_id == pid
    return False


def _visible_event(event_id: int, user: User, db: Session):
    event = db.query(InjuryEvent).filter(InjuryEvent.id == event_id).first()
    if event is None or not _can_see_event(user, event):
        raise HTTPException(status_code=404, detail="Event not found")
    return event


# ---------- who am I ----------

@app.get("/auth/me")
def me(current_user: User = Depends(get_current_user)):
    return user_to_dict(current_user)


# ---------- change own password ----------

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@app.post("/auth/change-password")
def change_password(request: ChangePasswordRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    new = request.new_password or ""

    if not verify_password(request.current_password or "", current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(new) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail="New password must be at least " + str(MIN_PASSWORD_LENGTH) + " characters")

    if len(new.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail="New password must be " + str(MAX_PASSWORD_LENGTH) + " characters or fewer")

    if new == request.current_password:
        raise HTTPException(status_code=400, detail="New password must be different from the current one")

    current_user.password_hash = pwd_context.hash(new)
    db.commit()

    print("[USERS]", current_user.username, "changed their password")

    return {"message": "Password changed"}


# ---------- medical assessments ----------

class AssessmentRequest(BaseModel):
    pain: str
    swelling: str
    tenderness: str
    rom: str
    weight: str
    neuro: str
    notes: str = ""
    imaging: str = ""
    impression: str
    status: str


def _assessment_for(user: User, record):
    """Coaches only get the outcome, never the clinical notes."""
    if record is None:
        return None
    if user.role in ("medical", "admin", "owner"):
        return record
    return {k: record.get(k) for k in ("event_id", "status", "saved_at", "saved_by")}


@app.get("/assessments")
def list_assessments(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    data = _load_json(ASSESSMENTS_FILE, {})
    ids = [int(k) for k in data.keys() if str(k).isdigit()]

    if not ids:
        return []

    events = db.query(InjuryEvent).filter(InjuryEvent.id.in_(ids)).all()
    visible = {e.id for e in events if _can_see_event(current_user, e)}

    # events deleted since (e.g. Gemini false alarm) are left out
    return [_assessment_for(current_user, data[str(i)]) for i in sorted(visible)]


@app.get("/events/{event_id}/assessment")
def get_assessment(event_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    _visible_event(event_id, current_user, db)

    record = _load_json(ASSESSMENTS_FILE, {}).get(str(event_id))

    return {"assessment": _assessment_for(current_user, record)}


@app.put("/events/{event_id}/assessment")
def save_assessment(event_id: int, request: AssessmentRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    if current_user.role != "medical":
        raise HTTPException(status_code=403, detail="Only medical staff can record assessments")

    event = _visible_event(event_id, current_user, db)

    fields = request.model_dump() if hasattr(request, "model_dump") else request.dict()

    for key in ("pain", "swelling", "tenderness", "rom", "weight", "neuro", "impression", "status"):
        fields[key] = (fields.get(key) or "").strip()
        if not fields[key]:
            raise HTTPException(status_code=400, detail="'" + key + "' is required")

    if fields["status"] not in ASSESSMENT_STATUSES:
        raise HTTPException(status_code=400, detail="Final status must be one of: " + ", ".join(ASSESSMENT_STATUSES))

    if len(fields["notes"]) > 4000 or len(fields["impression"]) > 4000:
        raise HTTPException(status_code=400, detail="Notes are limited to 4000 characters")

    data = _load_json(ASSESSMENTS_FILE, {})
    previous = data.get(str(event_id)) or {}

    record = dict(fields)
    record["event_id"] = event_id
    record["saved_by"] = current_user.username
    record["saved_at"] = _now_utc().isoformat()
    record["created_at"] = previous.get("created_at", record["saved_at"])
    record["revision"] = int(previous.get("revision", 0)) + 1

    data[str(event_id)] = record
    _save_json(ASSESSMENTS_FILE, data)

    # reviewed -> leaves the review queue; "Under observation" stays open
    event.resolved = fields["status"] not in ASSESSMENT_KEEPS_OPEN
    db.commit()

    print("[ASSESSMENT]", current_user.username, "saved event", event_id, "->", fields["status"])

    return {"message": "Assessment saved", "assessment": record, "resolved": event.resolved}


@app.patch("/events/{event_id}/reopen")
def reopen_event(event_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    if current_user.role not in ("medical", "admin"):
        raise HTTPException(status_code=403, detail="Only medical staff can reopen an event")

    event = _visible_event(event_id, current_user, db)
    event.resolved = False
    db.commit()

    return {"message": "Event reopened"}


# ---------- alert read state (per user) ----------

class AlertReadRequest(BaseModel):
    event_ids: list


@app.get("/alerts/read")
def get_alert_reads(current_user: User = Depends(get_current_user)):
    return {"event_ids": _load_json(ALERT_READS_FILE, {}).get(current_user.username, [])}


@app.post("/alerts/read")
def mark_alerts_read(request: AlertReadRequest, current_user: User = Depends(get_current_user)):

    try:
        new_ids = {int(i) for i in (request.event_ids or [])}
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="event_ids must be a list of numbers")

    data = _load_json(ALERT_READS_FILE, {})
    ids = set(data.get(current_user.username, [])) | new_ids
    data[current_user.username] = sorted(ids)[-MAX_READS_PER_USER:]
    _save_json(ALERT_READS_FILE, data)

    return {"event_ids": data[current_user.username]}


# ---------- detector progress for match pages (every role) ----------

# An Unidentified fall keeps looking for its player for this long (in video time).
# Same value as IDENTIFY_WINDOW_SECONDS in src/multi_player_injury.py.
IDENTIFY_WINDOW_SEC = 120


def _identifying_events(db, match_id, frame, fps):
    """Unidentified falls of the running match that are still being identified,
    with how far along the search is: [{"event_id": 12, "pct": 40}]."""
    if not match_id or not frame or not fps:
        return []
    video_now = float(frame) / float(fps)
    rows = [
        (e.id, e.video_time_sec) for e in (
            db.query(InjuryEvent)
            .filter(
                InjuryEvent.match_session_id.isnot(None),
                InjuryEvent.player_id.is_(None),
                InjuryEvent.video_time_sec.isnot(None),
            )
            .all()
        )
        if e.match_session_id == match_id and e.video_time_sec >= video_now - IDENTIFY_WINDOW_SEC
    ]
    out = []
    for event_id, t in rows:
        pct = int(round(100 * max(0.0, video_now - float(t)) / IDENTIFY_WINDOW_SEC))
        out.append({"event_id": event_id, "pct": max(1, min(99, pct))})
    return out


@app.get("/detector/status")
def detector_progress(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    status = _read_detector_status()
    control = _detector_control()

    # started from the website, still loading the model (no heartbeat yet)
    if _detector_launching(status, control):
        return {"state": "launching", "match_name": control.get("match_name"), "video": control.get("video"),
                "started_at": control.get("launched_at"), "identifying": []}

    if status is None:
        return {"state": "never"}

    seconds_ago = None
    try:
        seconds_ago = round((_now_utc() - datetime.fromisoformat(status.get("last_seen"))).total_seconds())
    except (TypeError, ValueError):
        pass

    state = status.get("state")
    if state in ("starting", "running") and (seconds_ago is None or seconds_ago > HEARTBEAT_STALE_SECONDS):
        state = "stopped"

    info = status.get("info") or {}
    progress = status.get("progress") or {}
    running = state in ("starting", "running")

    identifying = []
    if state in ("starting", "running"):
        try:
            identifying = _identifying_events(db, info.get("match_id"), progress.get("frame"), info.get("fps"))
        except Exception as e:
            print("[DETECTOR] Could not list falls being identified:", e)

    return {
        "state": state,
        "identifying": identifying,
        "match_id": info.get("match_id"),
        "match_name": info.get("match_name"),
        "frame": progress.get("frame"),
        "total_frames": info.get("total_frames"),
        "events": progress.get("events"),
        "started_at": status.get("started_at"),
        "finished_at": status.get("finished_at"),
        "seconds_since_last_signal": seconds_ago,
        "paused": bool(running and progress.get("paused")),
        "stop_requested": bool(running and control.get("stop") and control.get("match_id") in (None, info.get("match_id"))),
    }


# ---------- run the detector from the website (admin) ----------
# Videos live in <project>/videos. The admin uploads one (or picks one already there) and starts
# the analysis; the backend launches src/multi_player_injury.py (no window, live view on the website).
# Pause / resume / stop go through output/detector_control.json (encrypted), which the detector
# checks twice a second - this also works for a run started from a terminal.
# "Force stop" kills the process (clips still being written can be lost).

import subprocess

VIDEOS_DIR = os.path.join(PROJECT_ROOT, "videos")
VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v")
DETECTOR_SCRIPT = os.path.join(PROJECT_ROOT, "src", "multi_player_injury.py")
DETECTOR_CONTROL_FILE = os.path.join(PROJECT_ROOT, "output", "detector_control.json")
DETECTOR_LOG_FILE = os.path.join(PROJECT_ROOT, "output", "detector_run.log")
LAUNCH_GRACE_SECONDS = 240         # model + face gallery loading before the first heartbeat
MAX_VIDEO_BYTES = 8 * 1024 ** 3


def _detector_control():
    try:
        data = _load_json(DETECTOR_CONTROL_FILE, {})
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def _detector_launching(status, control):
    launched = _band_time(control.get("launched_at"))
    if launched is None or (_now_utc() - launched).total_seconds() > LAUNCH_GRACE_SECONDS:
        return False
    started = _band_time((status or {}).get("started_at"))
    return started is None or started < launched


def _detector_busy():
    status = _read_detector_status() or {}
    if _detector_launching(status, _detector_control()):
        return True
    last = _band_time(status.get("last_seen"))
    return status.get("state") in ("starting", "running") and last is not None \
        and (_now_utc() - last).total_seconds() <= HEARTBEAT_STALE_SECONDS


def _safe_video_name(name):
    base = os.path.basename(name or "").strip()
    if not base or base != (name or "").strip() or base.startswith(".") or not base.lower().endswith(VIDEO_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Video files must be MP4, AVI, MOV, MKV, WEBM or M4V")
    return base


@app.get("/admin/videos")
def list_videos(current_user: User = Depends(get_current_user)):
    _admin_only(current_user)
    out = []
    if os.path.isdir(VIDEOS_DIR):
        for name in sorted(os.listdir(VIDEOS_DIR)):
            full = os.path.join(VIDEOS_DIR, name)
            if os.path.isfile(full) and name.lower().endswith(VIDEO_EXTENSIONS):
                out.append({"name": name, "size_mb": round(os.path.getsize(full) / 1048576, 1),
                            "modified": datetime.fromtimestamp(os.path.getmtime(full), timezone.utc).isoformat()})
    return out


@app.put("/admin/videos/{filename}")
async def upload_video(filename: str, request: Request, current_user: User = Depends(get_current_user)):
    """Raw file body (not JSON), streamed to disk - works for match videos of several GB."""
    _admin_only(current_user)
    name = _safe_video_name(filename)
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    target = os.path.join(VIDEOS_DIR, name)
    if os.path.exists(target):
        raise HTTPException(status_code=409, detail=name + " already exists - rename the file or pick it from the list")
    tmp = target + ".part"
    size = 0
    try:
        with open(tmp, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_VIDEO_BYTES:
                    raise HTTPException(status_code=400, detail="Videos are limited to 8 GB")
                f.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The file is empty")
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print("[VIDEOS]", current_user.username, "uploaded", name, round(size / 1048576, 1), "MB")
    return {"name": name, "size_mb": round(size / 1048576, 1)}


class DetectorStartRequest(BaseModel):
    video: str
    match_name: Optional[str] = None


@app.post("/admin/detector/start")
def start_detector(request: DetectorStartRequest, current_user: User = Depends(get_current_user)):
    _admin_only(current_user)
    if _detector_busy():
        raise HTTPException(status_code=409, detail="An analysis is already running. Stop it first.")
    name = _safe_video_name(request.video)
    video = os.path.join(VIDEOS_DIR, name)
    if not os.path.isfile(video):
        raise HTTPException(status_code=404, detail="Video not found in the videos folder")
    match_name = " ".join((request.match_name or "").split())[:120] or None

    args = [sys.executable, "-u", DETECTOR_SCRIPT, video] + ([match_name] if match_name else [])
    env = dict(os.environ, DETECTOR_WINDOW="0", PYTHONIOENCODING="utf-8")
    os.makedirs(os.path.dirname(DETECTOR_LOG_FILE), exist_ok=True)
    log = open(DETECTOR_LOG_FILE, "w", encoding="utf-8")
    # no console window and no detector window: the picture is shown on the website (Watch Live)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(args, cwd=os.path.dirname(DETECTOR_SCRIPT), stdout=log, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, env=env, creationflags=flags)
    log.close()

    _save_json(DETECTOR_CONTROL_FILE, {"launched_at": _now_utc().isoformat(), "pid": proc.pid, "video": name,
                                       "match_name": match_name, "paused": False, "stop": False, "match_id": None,
                                       "started_by": current_user.username})
    print("[DETECTOR]", current_user.username, "started", name, "| pid", proc.pid)
    return {"message": "Analysis started", "pid": proc.pid, "video": name}


def _running_match_id():
    status = _read_detector_status() or {}
    return (status.get("info") or {}).get("match_id")


def _set_control(**changes):
    control = _detector_control()
    control.update(changes, match_id=_running_match_id())
    _save_json(DETECTOR_CONTROL_FILE, control)
    return control


@app.post("/admin/detector/pause")
def pause_detector(current_user: User = Depends(get_current_user)):
    _admin_only(current_user)
    if not _detector_busy():
        raise HTTPException(status_code=409, detail="No analysis is running")
    _set_control(paused=True)
    return {"message": "Pausing"}


@app.post("/admin/detector/resume")
def resume_detector(current_user: User = Depends(get_current_user)):
    _admin_only(current_user)
    _set_control(paused=False)
    return {"message": "Resuming"}


@app.post("/admin/detector/stop")
def stop_detector(force: bool = Query(False), current_user: User = Depends(get_current_user)):
    _admin_only(current_user)
    if not force:
        if not _detector_busy():
            raise HTTPException(status_code=409, detail="No analysis is running")
        _set_control(stop=True, paused=False)
        print("[DETECTOR]", current_user.username, "asked the detector to stop")
        return {"message": "Stopping - the clips and the report are being saved"}

    status = _read_detector_status() or {}
    pids = {p for p in ((status.get("info") or {}).get("pid"), _detector_control().get("pid")) if p}
    for pid in pids:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], capture_output=True)
        else:
            try:
                os.kill(int(pid), 9)
            except OSError:
                pass
    _save_json(DETECTOR_CONTROL_FILE, {"paused": False, "stop": False})
    if status.get("state") in ("starting", "running"):
        status["state"] = "finished"
        status["finished_at"] = _now_utc().isoformat()
        _save_json(DETECTOR_STATUS_FILE, status)
    print("[DETECTOR]", current_user.username, "force-stopped pid(s)", sorted(pids))
    return {"message": "Detector stopped"}


@app.get("/admin/detector/log")
def detector_log(lines: int = Query(60), current_user: User = Depends(get_current_user)):
    _admin_only(current_user)
    try:
        with open(DETECTOR_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            text_lines = f.read().splitlines()
    except OSError:
        text_lines = []
    return {"lines": text_lines[-max(1, min(lines, 400)):]}


# ---------- clip thumbnails ----------
# A small JPEG of the fall moment (middle of the clip), made the first time it is asked for
# and kept in output/clips/thumbs. Lists show it instead of loading the whole clip.

THUMBS_DIR = os.path.join(CLIPS_DIR, "thumbs")


@app.get("/thumbs/{name}")
def clip_thumbnail(name: str):
    base = os.path.basename(name)
    if base != name or not base.endswith(".jpg"):
        raise HTTPException(status_code=404, detail="Not found")
    clip = os.path.join(CLIPS_DIR, base[:-4])
    if not os.path.isfile(clip):
        raise HTTPException(status_code=404, detail="Not found")
    thumb = os.path.join(THUMBS_DIR, base)
    if not os.path.isfile(thumb) or os.path.getmtime(thumb) < os.path.getmtime(clip):
        import cv2
        cap = cv2.VideoCapture(clip)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frames = []
        while len(frames) < int(fps * 3) + 1:        # clips are 3 s before + 3 s after the fall
            ok, img = cap.read()
            if not ok:
                break
            frames.append(img)
        cap.release()
        if not frames:
            raise HTTPException(status_code=404, detail="Clip cannot be read")
        img = frames[-1]
        h, w = img.shape[:2]
        if w > 480:
            img = cv2.resize(img, (480, int(h * 480 / w)), interpolation=cv2.INTER_AREA)
        os.makedirs(THUMBS_DIR, exist_ok=True)
        cv2.imwrite(thumb, img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


# ---------- live detection view (src/live_view.py) ----------
# The detector posts its annotated frame (JPEG) a few times a second; only the newest one is
# kept, in memory (never on disk). Every logged-in user reads it through the encrypted channel:
# GET /live/frame?after=<seq> waits up to LIVE_WAIT_SEC for a newer frame than <seq>.

import asyncio

LIVE_MAX_BYTES = 3 * 1024 * 1024
LIVE_FRESH_SEC = 5            # no frame for this long = not live any more
LIVE_WAIT_SEC = 2.0

_live = {"jpeg": None, "seq": 0, "at": None}
_live_event = asyncio.Event()


@app.post("/live/frame")
async def live_frame_in(request: Request):
    global _live_event
    data = await request.body()
    if not data or len(data) > LIVE_MAX_BYTES or not data.startswith(b"\xff\xd8"):
        raise HTTPException(status_code=400, detail="Send one JPEG frame (max 3 MB)")
    _live.update(jpeg=data, seq=_live["seq"] + 1, at=_now_utc())
    event, _live_event = _live_event, asyncio.Event()
    event.set()              # wakes every viewer waiting for this frame
    return {"seq": _live["seq"]}


def _live_is_fresh():
    return _live["at"] is not None and (_now_utc() - _live["at"]).total_seconds() <= LIVE_FRESH_SEC


@app.get("/live/frame")
async def live_frame_out(after: int = Query(0), current_user: User = Depends(get_current_user)):
    if _live_is_fresh() and _live["seq"] <= after:
        try:
            await asyncio.wait_for(_live_event.wait(), timeout=LIVE_WAIT_SEC)
        except asyncio.TimeoutError:
            pass
    if not _live_is_fresh():
        return {"live": False, "seq": _live["seq"], "image": None}
    return {
        "live": True,
        "seq": _live["seq"],
        "at": _live["at"],
        "image": base64.b64encode(_live["jpeg"]).decode("ascii"),
    }


# ---------- player reference photos (known_players folder) ----------

class PhotoUploadRequest(BaseModel):
    filename: str
    data_base64: str


def _plain(s):
    s = "".join(ch for ch in unicodedata.normalize("NFD", str(s).upper()) if unicodedata.category(ch) != "Mn")
    return " ".join(s.split())


def _folder_matches(folder_name, player_name):
    """Same naming rules as src/player_identifier.py: "Name", "17 - Name", "17_Name"."""
    candidates = [folder_name]
    stripped = folder_name.lstrip("0123456789").lstrip(" _-.")
    if stripped != folder_name:
        candidates.append(stripped)
    if " - " in folder_name:
        candidates.extend(folder_name.split(" - "))
    target = _plain(player_name)
    return any(_plain(c) == target for c in candidates)


def _find_folder(root, player):
    if not os.path.isdir(root):
        return None
    for name in sorted(os.listdir(root)):
        if os.path.isdir(os.path.join(root, name)) and _folder_matches(name, player.name):
            return os.path.join(root, name)
    return None


def _player_folder(player, create=False):
    folder = _find_folder(KNOWN_PLAYERS_DIR, player)
    if folder is None and create:
        safe_name = re.sub(r'[<>:"/\\|?*]', "", player.name).strip()
        folder = os.path.join(KNOWN_PLAYERS_DIR, str(player.jersey_number) + " - " + safe_name)
        os.makedirs(folder, exist_ok=True)
    return folder


def _photo_player(player_id: int, user: User, db: Session):
    player = db.query(Player).filter(Player.id == player_id).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if user.role in ("coach", "owner") and player.team_id != user.team_id:
        raise HTTPException(status_code=403, detail="You can only manage photos of your own team's players")
    if user.role not in ("medical", "admin", "coach", "owner"):
        raise HTTPException(status_code=403, detail="Unknown role")
    return player


def _safe_photo_name(filename):
    name = os.path.basename(filename or "")
    if not name or name != filename or name.startswith(".") or not name.lower().endswith(PHOTO_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Invalid photo name")
    return name


def _image_files(folder):
    if folder is None or not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder) if f.lower().endswith(PHOTO_EXTENSIONS))


@app.get("/players/{player_id}/photos")
def list_player_photos(player_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    player = _photo_player(player_id, current_user, db)
    folder = _player_folder(player)

    photos = []
    for name in _image_files(folder):
        path = os.path.join(folder, name)
        photos.append({
            "name": name,
            "size": os.path.getsize(path),
            "uploaded_at": datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat(),
        })

    return {
        "player_id": player.id,
        "folder": os.path.basename(folder) if folder else str(player.jersey_number) + " - " + player.name,
        "photos": photos,
        "auto_learned": len(_image_files(_find_folder(AUTO_FACES_DIR, player))),
    }


@app.get("/players/{player_id}/photos/{filename}")
def get_player_photo(player_id: int, filename: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    player = _photo_player(player_id, current_user, db)
    name = _safe_photo_name(filename)
    folder = _player_folder(player)

    if folder is None or not os.path.isfile(os.path.join(folder, name)):
        raise HTTPException(status_code=404, detail="Photo not found")

    return FileResponse(os.path.join(folder, name))


@app.post("/players/{player_id}/photos")
def upload_player_photo(player_id: int, request: PhotoUploadRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    player = _photo_player(player_id, current_user, db)

    ext = os.path.splitext(request.filename or "")[1].lower()
    if ext not in PHOTO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP or BMP photos can be uploaded")

    data = request.data_base64 or ""
    if "," in data[:100]:
        data = data.split(",", 1)[1]          # accept "data:image/jpeg;base64,..."

    try:
        raw = base64.b64decode(data, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="The photo could not be read")

    if not raw:
        raise HTTPException(status_code=400, detail="The photo is empty")

    if len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail="Each photo must be 8 MB or smaller")

    folder = _player_folder(player, create=True)
    name = "upload_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ext

    with open(os.path.join(folder, name), "wb") as f:
        f.write(raw)

    print("[PHOTOS]", current_user.username, "added", name, "for", player.name)

    return {"message": "Photo uploaded", "name": name}


@app.delete("/players/{player_id}/photos/{filename}")
def delete_player_photo(player_id: int, filename: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    player = _photo_player(player_id, current_user, db)
    name = _safe_photo_name(filename)
    folder = _player_folder(player)
    path = os.path.join(folder, name) if folder else None

    if path is None or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Photo not found")

    os.remove(path)

    print("[PHOTOS]", current_user.username, "deleted", name, "for", player.name)

    return {"message": "Photo deleted"}


# ---------- previous injury history (output/injury_history.json) ----------
# Past injuries typed in by a coach (own team) or admin.
# Medical staff and admin see every player; a coach sees their own team.

INJURY_HISTORY_FILE = os.path.join(PROJECT_ROOT, "output", "injury_history.json")

HISTORY_SEVERITIES = ("Minor", "Moderate", "Severe")
HISTORY_STATUSES = ("Recovered", "Recovering", "Ongoing")
HISTORY_BODY_AREAS = (
    "Head", "Neck", "Shoulder", "Arm", "Elbow", "Wrist / Hand", "Chest", "Back",
    "Hip / Groin", "Thigh", "Hamstring", "Knee", "Lower leg", "Ankle", "Foot", "Other",
)


class InjuryHistoryRequest(BaseModel):
    injury: str
    body_area: str
    injury_date: str                 # YYYY-MM-DD
    severity: str
    status: str
    days_out: Optional[int] = None
    notes: str = ""


def _history_can_view(user: User, player: Player):
    if user.role in ("medical", "admin"):
        return True
    if user.role == "player":
        return player.id == _player_id_of(user)
    return user.role in ("coach", "owner") and player.team_id == user.team_id


def _history_can_edit(user: User, player: Player):
    if user.role == "admin":
        return True
    return user.role in ("coach", "owner") and player.team_id == user.team_id


def _history_player(player_id: int, user: User, db: Session, edit=False):
    player = db.query(Player).filter(Player.id == player_id).first()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if edit and not _history_can_edit(user, player):
        raise HTTPException(status_code=403, detail="Only admin or this player's coach can change injury history")
    if not edit and not _history_can_view(user, player):
        raise HTTPException(status_code=403, detail="Coaches can only see their own team's injury history")
    return player


def _history_fields(request: InjuryHistoryRequest):
    fields = request.model_dump() if hasattr(request, "model_dump") else request.dict()

    for key in ("injury", "body_area", "injury_date", "severity", "status"):
        fields[key] = (fields.get(key) or "").strip()
        if not fields[key]:
            raise HTTPException(status_code=400, detail="'" + key.replace("_", " ") + "' is required")

    if len(fields["injury"]) > 120:
        raise HTTPException(status_code=400, detail="Injury name is limited to 120 characters")

    if fields["body_area"] not in HISTORY_BODY_AREAS:
        raise HTTPException(status_code=400, detail="Body area must be one of: " + ", ".join(HISTORY_BODY_AREAS))

    if fields["severity"] not in HISTORY_SEVERITIES:
        raise HTTPException(status_code=400, detail="Severity must be one of: " + ", ".join(HISTORY_SEVERITIES))

    if fields["status"] not in HISTORY_STATUSES:
        raise HTTPException(status_code=400, detail="Status must be one of: " + ", ".join(HISTORY_STATUSES))

    try:
        day = datetime.strptime(fields["injury_date"], "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be in the format YYYY-MM-DD")

    if day > datetime.now().date():
        raise HTTPException(status_code=400, detail="The injury date cannot be in the future")

    if fields.get("days_out") is not None and not (0 <= int(fields["days_out"]) <= 1000):
        raise HTTPException(status_code=400, detail="Days out must be between 0 and 1000")

    fields["notes"] = (fields.get("notes") or "").strip()
    if len(fields["notes"]) > 1000:
        raise HTTPException(status_code=400, detail="Notes are limited to 1000 characters")

    return fields


def _history_record_out(record, player, user):
    out = dict(record)
    out["player_name"] = player.name if player else None
    out["jersey_number"] = player.jersey_number if player else None
    out["team_id"] = player.team_id if player else None
    out["team_name"] = player.team.name if player is not None and player.team is not None else None
    out["can_edit"] = bool(player) and _history_can_edit(user, player)
    return out


@app.get("/injury-history")
def list_injury_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    records = _load_json(INJURY_HISTORY_FILE, [])
    players = {p.id: p for p in db.query(Player).all()}

    result = []
    for r in records:
        player = players.get(r.get("player_id"))
        if player is not None and _history_can_view(current_user, player):
            result.append(_history_record_out(r, player, current_user))

    result.sort(key=lambda r: (r.get("injury_date") or "", r.get("id") or 0), reverse=True)
    return result


@app.post("/players/{player_id}/injury-history")
def add_injury_history(player_id: int, request: InjuryHistoryRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    player = _history_player(player_id, current_user, db, edit=True)
    fields = _history_fields(request)

    records = _load_json(INJURY_HISTORY_FILE, [])
    next_id = max([int(r.get("id") or 0) for r in records] + [0]) + 1

    record = dict(fields)
    record["id"] = next_id
    record["player_id"] = player.id
    record["added_by"] = current_user.username
    record["added_at"] = _now_utc().isoformat()

    records.append(record)
    _save_json(INJURY_HISTORY_FILE, records)

    print("[HISTORY]", current_user.username, "added", fields["injury"], "for", player.name)

    return {"message": "Injury added", "record": _history_record_out(record, player, current_user)}


@app.put("/injury-history/{record_id}")
def update_injury_history(record_id: int, request: InjuryHistoryRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    records = _load_json(INJURY_HISTORY_FILE, [])
    record = next((r for r in records if r.get("id") == record_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Injury record not found")

    player = _history_player(record.get("player_id"), current_user, db, edit=True)
    record.update(_history_fields(request))
    record["updated_by"] = current_user.username
    record["updated_at"] = _now_utc().isoformat()

    _save_json(INJURY_HISTORY_FILE, records)

    return {"message": "Injury updated", "record": _history_record_out(record, player, current_user)}


@app.delete("/injury-history/{record_id}")
def delete_injury_history(record_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    records = _load_json(INJURY_HISTORY_FILE, [])
    record = next((r for r in records if r.get("id") == record_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Injury record not found")

    player = _history_player(record.get("player_id"), current_user, db, edit=True)
    _save_json(INJURY_HISTORY_FILE, [r for r in records if r.get("id") != record_id])

    print("[HISTORY]", current_user.username, "deleted", record.get("injury"), "for", player.name)

    return {"message": "Injury deleted"}


# ============================================
# WRISTBAND - MATCH MODE v3 (AthleteGuard band / virtual_band.py)
# GET /band/{player_id}/status?key=...   ->  HIGH / MEDIUM / LOW / NONE  (plain text, for the ESP32)
# GET /band/{player_id}/summary?key=...  ->  the same with the counts and the players (JSON, for virtual_band.py)
# player_id 0 = every player (team doctor's band, includes Unidentified falls).
# The band shows the level for the WHOLE current match and only gets worse until the match is over:
#   any high-risk fall, or 2+ medium      -> HIGH
#   1 medium fall, or 3+ low falls        -> MEDIUM
#   1-2 low falls                          -> LOW
#   no falls                               -> NONE
# Re-running the same video: a fall found again replaces the earlier run's copy (create_event);
# earlier falls not found again still count as soon as the video reaches their time.
# Gemini false alarms do not count.
# BAND_HOLD_AFTER_MATCH_MIN minutes after the video finishes the band goes back to NONE.
# ============================================
from datetime import datetime as _band_dt, timedelta as _band_td, timezone as _band_tz
from fastapi.responses import PlainTextResponse as _BandText

BAND_KEY = os.environ.get("ATHLETEGUARD_BAND_KEY", "athleteguard-band-key")
BAND_HOLD_AFTER_MATCH_MIN = 10
BAND_STALE_SECONDS = 30


def _band_time(value):
    try:
        t = _band_dt.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=_band_tz.utc)


def _band_match(db):
    """(match_id, match_name, state, video_now). state: running / finished / over.
    video_now = seconds into the video while it is running (None = whole video)."""
    reader = globals().get("_read_detector_status")
    status = reader() if reader else None
    now = _band_dt.now(_band_tz.utc)
    if status and (status.get("info") or {}).get("match_id"):
        info = status.get("info") or {}
        progress = status.get("progress") or {}
        last_seen = _band_time(status.get("last_seen"))
        state = status.get("state")
        if state in ("starting", "running") and last_seen and (now - last_seen).total_seconds() <= BAND_STALE_SECONDS:
            video_now = None
            try:
                if progress.get("frame") is not None and info.get("fps"):
                    video_now = float(progress["frame"]) / float(info["fps"])
            except (TypeError, ValueError, ZeroDivisionError):
                video_now = None
            return info.get("match_id"), info.get("match_name"), "running", video_now
        ended = _band_time(status.get("finished_at")) or last_seen
        if ended and now - ended > _band_td(minutes=_band_hold()):
            return info.get("match_id"), info.get("match_name"), "over", None
        # BAND HOLD FIX: keep counting up to where the video got to, so the colour stays the same
        video_end = None
        try:
            if progress.get("frame") is not None and info.get("fps"):
                video_end = float(progress["frame"]) / float(info["fps"])
        except (TypeError, ValueError, ZeroDivisionError):
            video_end = None
        return info.get("match_id"), info.get("match_name"), "finished", video_end
    # no detector status yet: use the newest match
    m = db.query(MatchSession).order_by(MatchSession.id.desc()).first()
    return (m.id, m.name, "running", None) if m else (None, None, "over", None)


def _band_is_test(e):
    text = ((e.note or "") + " " + (e.injury_note or "")).lower()
    return "test only" in text or text.strip().startswith("test")


def _band_events(db, match_id, video_now):
    """BAND REUSE FIX: falls of this match + real detector falls of earlier runs of the same video
    that the video has already reached. Each fall is counted once."""
    rows = [e for e in _events_of_match(db, match_id) if not _band_is_test(e)]
    key_of = globals().get("_video_key")
    match = db.query(MatchSession).filter(MatchSession.id == match_id).first()
    key = key_of(match) if (key_of and match) else None
    if key and video_now is not None:
        seen = {e.id for e in rows}
        earlier = (db.query(InjuryEvent)
                   .filter(InjuryEvent.match_session_id.isnot(None),
                           InjuryEvent.video_time_sec.isnot(None))
                   .order_by(InjuryEvent.id.desc())
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


def _band_level(high, medium, low):
    if high or medium >= 2:
        return "HIGH"
    if medium or low >= 3:
        return "MEDIUM"
    if low:
        return "LOW"
    return "NONE"


_BAND_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}


def _band_summary(player_id, key, db):
    if key != _band_key():
        raise HTTPException(status_code=403, detail="Wrong band key")
    match_id, match_name, state, video_now = _band_match(db)
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    per_player = {}            # player id (None = Unidentified) -> name, jersey, team, counts
    counted = []               # the events behind the colour (shown in /summary)
    if match_id and state != "over":
        for e in _band_events(db, match_id, video_now):
            if player_id and e.player_id != player_id:
                continue
            if (e.gemini_verdict or "") == "false_alarm":
                continue
            risk = (e.risk or "").upper()
            if risk not in counts:
                continue
            counts[risk] += 1
            counted.append({"id": e.id, "match_id": e.match_session_id, "video_time_sec": e.video_time_sec,
                            "risk": risk, "player_id": e.player_id, "source": e.source})
            row = per_player.get(e.player_id)
            if row is None:
                p = e.player if e.player_id is not None else None
                row = {"player_id": e.player_id,
                       "name": p.name if p is not None else "Unidentified player",
                       "jersey_number": p.jersey_number if p is not None else None,
                       "team": p.team.name if (p is not None and p.team is not None) else None,
                       "HIGH": 0, "MEDIUM": 0, "LOW": 0}
                per_player[e.player_id] = row
            row[risk] += 1
    players = []
    for row in per_player.values():
        players.append({"player_id": row["player_id"], "name": row["name"], "jersey_number": row["jersey_number"],
                        "team": row["team"], "level": _band_level(row["HIGH"], row["MEDIUM"], row["LOW"]),
                        "falls": row["HIGH"] + row["MEDIUM"] + row["LOW"],
                        "high": row["HIGH"], "medium": row["MEDIUM"], "low": row["LOW"]})
    # worst first; Unidentified falls after named players with the same level
    players.sort(key=lambda r: (-_BAND_RANK[r["level"]], r["player_id"] is None, -r["falls"], r["name"]))
    level = _band_level(counts["HIGH"], counts["MEDIUM"], counts["LOW"])
    forced = _band_forced_level()
    return {"level": forced or level, "forced": bool(forced), "falls": sum(counts.values()),
            "high": counts["HIGH"], "medium": counts["MEDIUM"],
            "low": counts["LOW"], "match_id": match_id, "match_name": match_name, "match_state": state,
            "video_now": round(video_now, 1) if video_now is not None else None,
            "players": players, "events": counted}


# MANUAL BAND OVERRIDE (for testing the band):
# POST /band/force?key=...&level=HIGH|MEDIUM|LOW|NONE&minutes=5  -> every band shows that level
# POST /band/force?key=...&level=AUTO                             -> back to the real level
_band_force = {"level": None, "until": None}


def _band_forced_level():
    until = _band_force["until"]
    if _band_force["level"] and until and _band_dt.now(_band_tz.utc) > until:
        _band_force["level"] = None
    return _band_force["level"]


@app.post("/band/force")
def band_force(key: str = Query(""), level: str = Query("AUTO"), minutes: int = Query(5, ge=1, le=240)):
    if key != _band_key():
        raise HTTPException(status_code=403, detail="Wrong band key")
    level = level.upper()
    if level == "AUTO":
        _band_force.update(level=None, until=None)
        return {"forced": False, "message": "Band back to the real level"}
    if level not in _BAND_RANK:
        raise HTTPException(status_code=400, detail="level must be HIGH, MEDIUM, LOW, NONE or AUTO")
    _band_force.update(level=level, until=_band_dt.now(_band_tz.utc) + _band_td(minutes=minutes))
    return {"forced": True, "level": level, "until": _band_force["until"].isoformat()}


@app.get("/band/{player_id}/status", response_class=_BandText)
def band_status(player_id: int, key: str = Query(""), db: Session = Depends(get_db)):
    return _band_summary(player_id, key, db)["level"]


@app.get("/band/{player_id}/summary")
def band_summary(player_id: int, key: str = Query(""), db: Session = Depends(get_db)):
    return _band_summary(player_id, key, db)


# ============================================
# ADMIN SETTINGS (Settings page for the admin)
#   detection  -> output/detection_settings.json (read by src/multi_player_injury.py at start)
#   wristband  -> output/app_settings.json (band key + how long the band keeps its colour)
#   data       -> clip storage clean-up and a full JSON backup
# Only the admin can read or change these.
# ============================================
from fastapi.responses import JSONResponse as _AdmJSON
from datetime import datetime as _adm_dt, timezone as _adm_tz

DETECTION_SETTINGS_FILE = os.path.join(PROJECT_ROOT, "output", "detection_settings.json")
APP_SETTINGS_FILE = os.path.join(PROJECT_ROOT, "output", "app_settings.json")

# name -> (default, min, max, kind)
DETECTION_FIELDS = {
    "fall_angle": (60, 30, 85, "int"),                  # falling movement: body tilt from vertical (deg)
    "fall_downward_ratio": (0.18, 0.05, 0.6, "float"),  # body must drop this share of its height
    "lying_angle": (55, 30, 85, "int"),                 # lying down: torso tilt from vertical (deg)
    "lying_aspect_ratio": (1.2, 0.8, 3.0, "float"),     # lying down: box width / height
    "keypoint_confidence": (0.35, 0.1, 0.9, "float"),   # body points below this are ignored
    "person_confidence": (0.45, 0.1, 0.9, "float"),     # people below this are ignored
    "risk_medium_from": (12, 1, 100, "float"),          # movement (% of height per frame) for MEDIUM
    "risk_high_from": (22, 2, 150, "float"),            # ... and for HIGH
    "fall_cooldown_seconds": (5, 1, 60, "int"),         # same player can fall again after this
    "gemini_check": (True, None, None, "bool"),         # Gemini double-checks every fall
    "gemini_delete_min_confidence": (0.75, 0.5, 1.0, "float"),  # Gemini this sure of a false alarm -> deleted
}


def _admin_only(user: User):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the admin can change settings")


def _detection_settings():
    saved = _load_json(DETECTION_SETTINGS_FILE, {})
    saved = saved if isinstance(saved, dict) else {}
    return {k: saved.get(k, d[0]) for k, d in DETECTION_FIELDS.items()}


def _app_settings():
    saved = _load_json(APP_SETTINGS_FILE, {})
    return saved if isinstance(saved, dict) else {}


def _gemini_delete_min():
    try:
        return float(_detection_settings()["gemini_delete_min_confidence"])
    except (TypeError, ValueError):
        return GEMINI_DELETE_MIN_CONFIDENCE


def _band_key():
    return (_app_settings().get("band") or {}).get("key") or BAND_KEY


def _band_hold():
    try:
        return int((_app_settings().get("band") or {}).get("hold_minutes", BAND_HOLD_AFTER_MATCH_MIN))
    except (TypeError, ValueError):
        return BAND_HOLD_AFTER_MATCH_MIN


def _env_has(name):
    """True if the key is set (environment or the project's .env). Never returns the value."""
    if os.environ.get(name):
        return True
    try:
        with open(os.path.join(PROJECT_ROOT, ".env"), "r", encoding="utf-8") as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                if k.strip() == name and v.strip().strip('"').strip("'"):
                    return True
    except OSError:
        pass
    return False


def _clips_info():
    count, size, oldest = 0, 0, None
    if os.path.isdir(CLIPS_DIR):
        for name in os.listdir(CLIPS_DIR):
            full = os.path.join(CLIPS_DIR, name)
            if os.path.isfile(full):
                count += 1
                size += os.path.getsize(full)
                m = os.path.getmtime(full)
                oldest = m if oldest is None else min(oldest, m)
    days = None if oldest is None else round((_adm_dt.now().timestamp() - oldest) / 86400, 1)
    return {"count": count, "size_mb": round(size / 1048576, 1), "oldest_days": days}


@app.get("/admin/settings")
def admin_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _admin_only(current_user)
    band = _app_settings().get("band") or {}
    return {
        "detection": _detection_settings(),
        "detection_defaults": {k: d[0] for k, d in DETECTION_FIELDS.items()},
        "detection_limits": {k: [d[1], d[2]] for k, d in DETECTION_FIELDS.items() if d[3] != "bool"},
        "band": {"key": _band_key(), "hold_minutes": _band_hold(), "custom_key": bool(band.get("key"))},
        "info": {
            "gemini_key": _env_has("GEMINI_API_KEY"),
            "gemini_injury_key": _env_has("GEMINI_INJURY_API_KEY"),
            "clips": _clips_info(),
            "events": db.query(InjuryEvent).count(),
            "players": db.query(Player).count(),
            "matches": db.query(MatchSession).count(),
        },
    }


@app.put("/admin/settings/detection")
def save_detection_settings(request: dict, current_user: User = Depends(get_current_user)):
    _admin_only(current_user)
    out = _detection_settings()
    for name, (default, lo, hi, kind) in DETECTION_FIELDS.items():
        if name not in (request or {}):
            continue
        value = request[name]
        label = name.replace("_", " ")
        if kind == "bool":
            out[name] = bool(value)
            continue
        try:
            value = int(value) if kind == "int" else round(float(value), 3)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="'" + label + "' must be a number")
        if value < lo or value > hi:
            raise HTTPException(status_code=400, detail="'" + label + "' must be between " + str(lo) + " and " + str(hi))
        out[name] = value
    if out["risk_high_from"] <= out["risk_medium_from"]:
        raise HTTPException(status_code=400, detail="High risk must start above medium risk")
    out["updated_by"] = current_user.username
    out["updated_at"] = _adm_dt.now(_adm_tz.utc).isoformat()
    _save_json(DETECTION_SETTINGS_FILE, out)
    print("[SETTINGS]", current_user.username, "saved detection settings")
    return {"detection": {k: out[k] for k in DETECTION_FIELDS}}


@app.post("/admin/settings/detection/reset")
def reset_detection_settings(current_user: User = Depends(get_current_user)):
    _admin_only(current_user)
    if os.path.isfile(DETECTION_SETTINGS_FILE):
        os.remove(DETECTION_SETTINGS_FILE)
    return {"detection": _detection_settings()}


@app.put("/admin/settings/band")
def save_band_settings(request: dict, current_user: User = Depends(get_current_user)):
    _admin_only(current_user)
    data = _app_settings()
    band = dict(data.get("band") or {})
    if "key" in (request or {}):
        key = str(request.get("key") or "").strip()
        if key and (len(key) < 8 or len(key) > 64 or not all(c.isalnum() or c in "-_" for c in key)):
            raise HTTPException(status_code=400, detail="Band key: 8-64 letters, numbers, - or _")
        band["key"] = key or None       # empty = back to the default key
    if "hold_minutes" in (request or {}):
        try:
            hold = int(request.get("hold_minutes"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="'hold minutes' must be a number")
        if hold < 0 or hold > 180:
            raise HTTPException(status_code=400, detail="'hold minutes' must be between 0 and 180")
        band["hold_minutes"] = hold
    data["band"] = band
    _save_json(APP_SETTINGS_FILE, data)
    print("[SETTINGS]", current_user.username, "saved wristband settings")
    return {"band": {"key": _band_key(), "hold_minutes": _band_hold(), "custom_key": bool(band.get("key"))}}


class ClipCleanupRequest(BaseModel):
    older_than_days: int


@app.post("/admin/clips/cleanup")
def cleanup_clips(request: ClipCleanupRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deletes clip files older than N days. The events stay; they just lose their clip."""
    _admin_only(current_user)
    days = request.older_than_days
    if days < 1 or days > 3650:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 3650")
    cutoff = _adm_dt.now().timestamp() - days * 86400
    deleted, freed = [], 0
    if os.path.isdir(CLIPS_DIR):
        for name in os.listdir(CLIPS_DIR):
            full = os.path.join(CLIPS_DIR, name)
            if os.path.isfile(full) and os.path.getmtime(full) < cutoff:
                size = os.path.getsize(full)
                try:
                    os.remove(full)
                except OSError:
                    continue
                deleted.append(name)
                freed += size
    if deleted:
        gone = set(deleted)
        for e in db.query(InjuryEvent).filter(InjuryEvent.clip_path.isnot(None)).all():
            if e.clip_path in gone:
                e.clip_path = None
        db.commit()
    print("[SETTINGS]", current_user.username, "deleted", len(deleted), "clips older than", days, "days")
    return {"deleted": len(deleted), "freed_mb": round(freed / 1048576, 1), "clips": _clips_info()}


@app.get("/admin/backup")
def admin_backup(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Everything as one JSON file: events, teams, players, matches and the saved JSON stores."""
    _admin_only(current_user)
    def plain(obj, fields):
        return {f: getattr(obj, f, None) for f in fields}
    stores = {}
    out_dir = os.path.join(PROJECT_ROOT, "output")
    if os.path.isdir(out_dir):
        for name in sorted(os.listdir(out_dir)):
            if name.endswith(".json") and name not in ("detector_status.json",):
                stores[name] = _load_json(os.path.join(out_dir, name), None)
    data = {
        "exported_at": _adm_dt.now(_adm_tz.utc).isoformat(),
        "exported_by": current_user.username,
        "teams": [plain(t, ("id", "name")) for t in db.query(Team).all()],
        "players": [plain(p, ("id", "name", "jersey_number", "team_id")) for p in db.query(Player).all()],
        "matches": [plain(m, ("id", "name", "video_source", "date", "team_a_id", "team_b_id")) for m in db.query(MatchSession).all()],
        "events": [event_to_dict(e) for e in db.query(InjuryEvent).order_by(InjuryEvent.id).all()],
        "stores": stores,
    }
    name = "athleteguard-backup-" + _adm_dt.now().strftime("%Y%m%d-%H%M") + ".json"
    return _AdmJSON(content=_json.loads(_json.dumps(data, default=str)), headers={"Content-Disposition": 'attachment; filename="' + name + '"'})
