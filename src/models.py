from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import object_session
from database import Base
from crypto_store import (
    EncryptedBool, EncryptedDateTime, EncryptedFloat, EncryptedInt, EncryptedText,
    lookup_hash, now_utc,
)

# ============================================
# ENCRYPTION
# Every column is stored encrypted (AES-256-GCM, see crypto_store.py) and is decrypted
# when read - including the links between tables (team_id, player_id, match_session_id).
# Only each row's own id is plain: it is the row number Postgres needs to find a row.
# Encrypted columns cannot be compared, joined or sorted in SQL - filter and sort in
# Python (NULL checks still work: a missing value is stored as NULL, not encrypted).
# The links below (event.player, player.team ...) are read-only properties that load the
# linked row by its decrypted id - there are no SQL joins and no database foreign-key
# constraints on encrypted links. To change a link, set the id column (e.g. player_id).
# ============================================


def _link(target, column):
    def get(self):
        value = getattr(self, column)
        session = object_session(self)
        if value is None or session is None:
            return None
        return session.get(globals()[target], value)
    return property(get)


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(EncryptedText, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(EncryptedText, nullable=False)
    # keyed hash of the lower-case username: finds a login without decrypting every row
    username_lookup = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(EncryptedText, nullable=False)
    role = Column(EncryptedText, nullable=False)
    team_id = Column(EncryptedInt, nullable=True)

    team = _link("Team", "team_id")

    def __init__(self, **kw):
        super().__init__(**kw)
        if self.username is not None and not self.username_lookup:
            self.username_lookup = lookup_hash(self.username)


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(EncryptedInt, nullable=False)
    name = Column(EncryptedText, nullable=False)
    jersey_number = Column(EncryptedInt, nullable=False)

    team = _link("Team", "team_id")


# ============================================
# MATCH SESSION
# One row per detection run / video, so events
# from different matches can be told apart.
# ============================================

class MatchSession(Base):
    __tablename__ = "match_sessions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(EncryptedText, nullable=True)
    video_source = Column(EncryptedText, nullable=True)
    date = Column(EncryptedDateTime, default=now_utc)
    team_a_id = Column(EncryptedInt, nullable=True)
    team_b_id = Column(EncryptedInt, nullable=True)


# ============================================
# INJURY EVENT
# player_id is nullable: a fall is saved right
# away as "Unidentified" and the player is filled
# in later on the same row once identified.
# identified_by / id_detail / id_confidence record
# HOW the player was recognised (jersey, face, gemini or manual).
# gemini_* columns hold Gemini's second opinion on the clip.
# ============================================

class InjuryEvent(Base):
    __tablename__ = "injury_events"

    id = Column(Integer, primary_key=True, index=True)
    match_session_id = Column(EncryptedInt, nullable=True)
    player_id = Column(EncryptedInt, nullable=True)
    event_type = Column(EncryptedText, nullable=False)
    region = Column(EncryptedText, nullable=True)
    risk = Column(EncryptedText, nullable=True)
    movement = Column(EncryptedFloat, nullable=True)
    note = Column(EncryptedText, nullable=True)
    injury_note = Column(EncryptedText, nullable=True)
    clip_path = Column(EncryptedText, nullable=True)
    source = Column(EncryptedText, nullable=False, default="ai")
    resolved = Column(EncryptedBool, default=False)
    track_id = Column(EncryptedInt, nullable=True)
    video_time_sec = Column(EncryptedFloat, nullable=True)
    identified_by = Column(EncryptedText, nullable=True)
    id_detail = Column(EncryptedText, nullable=True)
    id_confidence = Column(EncryptedFloat, nullable=True)
    identified_at = Column(EncryptedDateTime, nullable=True)
    # Gemini second opinion (see src/gemini_verifier.py)
    gemini_verdict = Column(EncryptedText, nullable=True)        # real_fall / false_alarm / unsure / error
    gemini_confidence = Column(EncryptedFloat, nullable=True)
    gemini_reason = Column(EncryptedText, nullable=True)
    gemini_description = Column(EncryptedText, nullable=True)
    gemini_jersey = Column(EncryptedInt, nullable=True)
    gemini_team = Column(EncryptedText, nullable=True)
    gemini_jersey_confidence = Column(EncryptedFloat, nullable=True)
    gemini_checked_at = Column(EncryptedDateTime, nullable=True)
    timestamp = Column(EncryptedDateTime, default=now_utc)

    player = _link("Player", "player_id")
    match = _link("MatchSession", "match_session_id")
