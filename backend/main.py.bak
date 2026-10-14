import os
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import or_, text
from sqlalchemy.orm import Session, object_session
from sqlalchemy.sql import func

from database import get_db, SessionLocal, Base
from models import User, Player, InjuryEvent, Team, MatchSession
from auth import verify_password, create_access_token, decode_access_token


app = FastAPI()

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
# ============================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

MIGRATIONS = [
    "ALTER TABLE match_sessions ADD COLUMN IF NOT EXISTS name VARCHAR",
    "ALTER TABLE match_sessions ADD COLUMN IF NOT EXISTS video_source VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS region VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS risk VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS movement DOUBLE PRECISION",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS note VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS source VARCHAR NOT NULL DEFAULT 'ai'",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS resolved BOOLEAN DEFAULT FALSE",
    'ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS "timestamp" TIMESTAMPTZ DEFAULT now()',
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS match_session_id INTEGER REFERENCES match_sessions(id)",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS injury_note VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS clip_path VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS identified_at TIMESTAMPTZ",
    "ALTER TABLE injury_events ALTER COLUMN player_id DROP NOT NULL",
    # v3 — how and where the player was identified
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS track_id INTEGER",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS video_time_sec DOUBLE PRECISION",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS identified_by VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS id_detail VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS id_confidence DOUBLE PRECISION",
    # v4 — Gemini second opinion
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS gemini_verdict VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS gemini_confidence DOUBLE PRECISION",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS gemini_reason VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS gemini_description VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS gemini_jersey INTEGER",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS gemini_team VARCHAR",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS gemini_jersey_confidence DOUBLE PRECISION",
    "ALTER TABLE injury_events ADD COLUMN IF NOT EXISTS gemini_checked_at TIMESTAMPTZ",
]

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

# (username, team, password used only when the account does not exist yet)
COACH_ACCOUNTS = [
    ("coach1", "Netherlands", "coach1pass"),
    ("coach2", "Portugal", "coach2pass"),
]


def bootstrap_data():

    probe = SessionLocal()
    engine = probe.get_bind()
    probe.close()

    # 1. tables + columns
    Base.metadata.create_all(bind=engine)

    for sql in MIGRATIONS:
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
        except Exception as e:
            print("[BOOTSTRAP] migration skipped:", sql[:60], "|", e)

    db = SessionLocal()

    try:
        # 2. teams + players
        teams = {}

        for team_name, roster in ROSTERS.items():

            team = db.query(Team).filter(Team.name == team_name).first()

            if team is None:
                placeholder = db.query(Team).filter(Team.name == PLACEHOLDER_TEAMS[team_name]).first()
                if placeholder is not None:
                    placeholder.name = team_name
                    team = placeholder

            if team is None:
                team = Team(name=team_name)
                db.add(team)
                db.flush()

            teams[team_name] = team

            existing = {}
            for p in db.query(Player).filter(Player.team_id == team.id).all():
                existing.setdefault(p.jersey_number, p)

            for number, name in roster:
                if number not in existing:
                    db.add(Player(team_id=team.id, name=name, jersey_number=number))
                    print("[BOOTSTRAP] added player:", team_name, "#" + str(number), name)

        db.flush()

        # 3. coach accounts
        for username, team_name, password in COACH_ACCOUNTS:

            user = db.query(User).filter(User.username == username).first()

            if user is None:
                db.add(User(
                    username=username,
                    password_hash=pwd_context.hash(password),
                    role="coach",
                    team_id=teams[team_name].id,
                ))
                print("[BOOTSTRAP] created", username, "->", team_name, "| password:", password)

            elif user.team_id != teams[team_name].id or user.role != "coach":
                user.role = "coach"
                user.team_id = teams[team_name].id
                print("[BOOTSTRAP] assigned", username, "->", team_name)

        # 4. admin (only if none exists)
        if db.query(User).filter(User.role == "admin").first() is None:
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
    """Which copy of a duplicate to keep: staff pick > identified (by confidence) > has clip > oldest."""
    return (
        1 if e.identified_by == "manual" else 0,
        1 if e.player_id is not None else 0,
        e.id_confidence or 0.0,
        1 if e.clip_path else 0,
        -e.id,
    )


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
    q = db.query(InjuryEvent.id).filter(InjuryEvent.clip_path == clip_path)
    if exclude_ids:
        q = q.filter(InjuryEvent.id.notin_(list(exclude_ids)))
    return q.first() is not None


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

def get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)):

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.replace("Bearer ", "")

    payload = decode_access_token(token)

    if payload is None:
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
                _ai_injury_cache["data"] = _json.load(f)
        except (OSError, ValueError):
            _ai_injury_cache["data"] = {}
        _ai_injury_cache["mtime"] = mtime
    return _ai_injury_cache["data"]


def _ai_injury_for(event_id):
    return _ai_injury_all().get(str(event_id))


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
        "source": e.source,
        "resolved": e.resolved,
        "timestamp": e.timestamp,
    }


# ============================================
# LOGIN
# ============================================

@app.post("/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.username == request.username).first()

    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({
        "user_id": user.id,
        "role": user.role,
        "team_id": user.team_id
    })

    return {
        "access_token": token,
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

    matches = db.query(MatchSession).order_by(MatchSession.date.desc()).all()

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
        event_type=request.event_type,
        region=request.region,
        risk=request.risk,
        movement=request.movement,
        injury_note=request.injury_note,
        clip_path=request.clip_path,
        source=request.source,
        track_id=request.track_id,
        video_time_sec=request.video_time_sec,
    )

    if request.player_id is not None:
        event.identified_at = func.now()
        event.identified_by = request.identified_by
        event.id_detail = request.id_detail
        event.id_confidence = request.id_confidence

    # Same fall already saved by an earlier run of this video? Reuse that event.
    existing = _find_duplicate(db, event)

    if existing is not None:

        # fill in the player if the earlier copy never got one (never overrides staff)
        if existing.player_id is None and event.player_id is not None:
            existing.player_id = event.player_id
            existing.identified_at = func.now()
            existing.identified_by = event.identified_by
            existing.id_detail = event.id_detail
            existing.id_confidence = event.id_confidence
            db.commit()

        return {
            "message": "Duplicate of an event from an earlier run of this video",
            "event_id": existing.id,
            "duplicate": True,
        }

    db.add(event)
    db.commit()
    db.refresh(event)

    return {"message": "Event recorded", "event_id": event.id, "duplicate": False}


def _find_duplicate(db, new_event):
    """Closest matching event from an earlier run of the same video, or None."""

    if new_event.match_session_id is None or new_event.video_time_sec is None:
        return None
    if (new_event.source or "ai") != "ai":
        return None

    match = db.query(MatchSession).filter(MatchSession.id == new_event.match_session_id).first()
    key = _video_key(match)

    if key is None:
        return None

    candidates = (
        db.query(InjuryEvent)
        .join(MatchSession, InjuryEvent.match_session_id == MatchSession.id)
        .filter(
            InjuryEvent.match_session_id != new_event.match_session_id,
            InjuryEvent.video_time_sec.isnot(None),
            InjuryEvent.video_time_sec >= new_event.video_time_sec - DUPLICATE_WINDOW_SEC,
            InjuryEvent.video_time_sec <= new_event.video_time_sec + DUPLICATE_WINDOW_SEC,
        )
        .all()
    )

    matches = [c for c in candidates if _same_fall(new_event, c, key_a=key)]

    if not matches:
        return None

    matches.sort(key=lambda c: abs(c.video_time_sec - new_event.video_time_sec))
    return matches[0]


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
            event.identified_at = func.now()
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
    if (not jersey_only and verdict == "false_alarm" and confidence >= GEMINI_DELETE_MIN_CONFIDENCE
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
    event.gemini_checked_at = func.now()

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

        player = (
            db.query(Player)
            .join(Team, Team.id == Player.team_id)
            .filter(Team.name.ilike(request.team.strip()), Player.jersey_number == request.jersey_number)
            .first()
        )

        if player is not None and player.id != event.player_id:

            ours = event.id_confidence or 0.0

            if event.player_id is None or jersey_conf > ours:

                previous = (
                    event.player.name + " (" + str(round(ours * 100)) + "%)"
                    if event.player is not None else "Unidentified"
                )

                event.player_id = player.id
                event.identified_at = func.now()
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

        if current_user.role != "coach":
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
    event.identified_at = func.now()
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
        event_type=request.event_type,
        note=request.note,
        risk=request.risk,
        source="manual",
        identified_by="manual",
        id_detail="logged by " + current_user.username,
    )

    event.identified_at = func.now()

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

    query = db.query(InjuryEvent).outerjoin(Player, InjuryEvent.player_id == Player.id)

    if current_user.role in ("medical", "admin"):
        pass

    elif current_user.role == "coach":
        query = query.filter(
            or_(
                Player.team_id == current_user.team_id,
                InjuryEvent.player_id.is_(None)
            )
        )

    elif current_user.role == "player":
        # a player only sees their own falls
        query = query.filter(InjuryEvent.player_id == (_player_id_of(current_user) or -1))

    else:
        raise HTTPException(status_code=403, detail="Unknown role")

    if match_id is not None:
        query = query.filter(InjuryEvent.match_session_id == match_id)

    events = query.order_by(InjuryEvent.timestamp.desc()).all()

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

    players = query.order_by(Player.team_id, Player.jersey_number).all()

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

    elif current_user.role in ("coach", "player"):
        teams = db.query(Team).filter(Team.id == current_user.team_id).all()

    else:
        raise HTTPException(status_code=403, detail="Unknown role")

    result = []

    for t in teams:

        players = (
            db.query(Player)
            .filter(Player.team_id == t.id)
            .order_by(Player.jersey_number)
            .all()
        )

        coaches = db.query(User).filter(User.role == "coach", User.team_id == t.id).all()

        rows = []
        team_total = 0
        team_high = 0

        for p in players:

            total = (
                db.query(func.count(InjuryEvent.id))
                .filter(InjuryEvent.player_id == p.id)
                .scalar()
            ) or 0

            high = (
                db.query(func.count(InjuryEvent.id))
                .filter(InjuryEvent.player_id == p.id, InjuryEvent.risk == "HIGH")
                .scalar()
            ) or 0

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

USER_ROLES = ("admin", "medical", "coach", "player")

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
    username: str
    password: str
    role: str                         # admin / medical / coach / player
    team_id: Optional[int] = None     # required for coach, ignored otherwise
    player_id: Optional[int] = None   # required for player: the roster player this login belongs to


def user_to_dict(u: User):

    out = {
        "id": u.id,
        "username": u.username,
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
            out["coaches"] = [c.username for c in session.query(User).filter(User.role == "coach", User.team_id == player.team_id).all()]

    return out


def _require_admin(current_user: User):

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can manage user accounts")


@app.get("/admin/users")
def list_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    _require_admin(current_user)

    users = db.query(User).order_by(User.role, User.username).all()

    return [user_to_dict(u) for u in users]


@app.post("/admin/users")
def create_user(
    request: UserCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    _require_admin(current_user)

    username = (request.username or "").strip()
    password = request.password or ""
    role = (request.role or "").strip().lower()

    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    if any(ch.isspace() for ch in username):
        raise HTTPException(status_code=400, detail="Username cannot contain spaces")

    if len(username) > 50:
        raise HTTPException(status_code=400, detail="Username must be 50 characters or fewer")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail="Password must be at least " + str(MIN_PASSWORD_LENGTH) + " characters")

    if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail="Password must be " + str(MAX_PASSWORD_LENGTH) + " characters or fewer")

    if role not in USER_ROLES:
        raise HTTPException(status_code=400, detail="Role must be admin, medical, coach or player")

    taken = db.query(User).filter(func.lower(User.username) == username.lower()).first()

    if taken is not None:
        raise HTTPException(status_code=409, detail="Username '" + username + "' is already taken")

    team_id = None

    if role == "coach":

        if request.team_id is None:
            raise HTTPException(status_code=400, detail="Pick the team this coach manages")

        team = db.query(Team).filter(Team.id == request.team_id).first()

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

    db.add(user)
    db.commit()
    db.refresh(user)

    if player is not None:
        accounts = _player_accounts()
        accounts[str(user.id)] = player.id
        _save_json(PLAYER_ACCOUNTS_FILE, accounts)

    print("[USERS]", current_user.username, "created", username, "(" + role + ")")

    return {"message": "User created", "user": user_to_dict(user)}


@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    _require_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    if user.role == "admin" and db.query(User).filter(User.role == "admin").count() <= 1:
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
    try:
        with open(DETECTOR_STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


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

    tmp = DETECTOR_STATUS_FILE + ".tmp"
    try:
        os.makedirs(os.path.dirname(DETECTOR_STATUS_FILE), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(current, f, default=str)
        os.replace(tmp, DETECTOR_STATUS_FILE)
    except OSError as e:
        raise HTTPException(status_code=500, detail="Could not save detector status: " + str(e))

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

    _require_admin(current_user)

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
        by_method = (
            db.query(InjuryEvent.identified_by, func.count(InjuryEvent.id))
            .filter(InjuryEvent.player_id.isnot(None))
            .group_by(InjuryEvent.identified_by)
            .all()
        )
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
        m = db.query(MatchSession).order_by(MatchSession.date.desc()).first()
        if m is not None:
            ev_count = db.query(func.count(InjuryEvent.id)).filter(InjuryEvent.match_session_id == m.id).scalar() or 0
            ev_ident = (
                db.query(func.count(InjuryEvent.id))
                .filter(InjuryEvent.match_session_id == m.id, InjuryEvent.player_id.isnot(None))
                .scalar()
            ) or 0
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
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_json(path, data):
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, default=str, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError as e:
        raise HTTPException(status_code=500, detail="Could not save: " + str(e))


def _can_see_event(user: User, event: InjuryEvent):
    """Medical/admin see every event. A coach sees their team's events and every Unidentified fall."""
    if user.role in ("medical", "admin"):
        return True
    if user.role == "coach":
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
    if user.role in ("medical", "admin"):
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

@app.get("/detector/status")
def detector_progress(current_user: User = Depends(get_current_user)):

    status = _read_detector_status()

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

    return {
        "state": state,
        "match_id": info.get("match_id"),
        "match_name": info.get("match_name"),
        "frame": progress.get("frame"),
        "total_frames": info.get("total_frames"),
        "events": progress.get("events"),
        "started_at": status.get("started_at"),
        "finished_at": status.get("finished_at"),
        "seconds_since_last_signal": seconds_ago,
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
    if user.role == "coach" and player.team_id != user.team_id:
        raise HTTPException(status_code=403, detail="Coaches can only manage photos of their own team's players")
    if user.role not in ("medical", "admin", "coach"):
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
    return user.role == "coach" and player.team_id == user.team_id


def _history_can_edit(user: User, player: Player):
    if user.role == "admin":
        return True
    return user.role == "coach" and player.team_id == user.team_id


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