"""
encrypt_database.py - one-time switch of the existing data to encrypted storage.

Run it ONCE from the backend folder, with the backend and the detector stopped:
    python crypto_store.py --new-key      (only if ATHLETEGUARD_DATA_KEY is not set yet)
    python encrypt_database.py

What it does:
  1. Saves an (encrypted) copy of every table to output/db_backup_before_encryption.json
  2. In ONE transaction (all or nothing):
       - every column becomes TEXT, including the links between tables (only each row's
         own id stays a plain number; the foreign-key constraints are removed)
       - every value is encrypted with AES-256-GCM
       - users get username_lookup (keyed hash used to find a login)
  3. Encrypts the JSON stores in output/ and the names in src/player_identifications.db

Safe to run again: values that are already encrypted are left alone.
Tip: also take a normal Postgres backup first:  pg_dump -U injury_app_user injury_detection_db > before.sql
"""

import os
import sqlite3
import sys
from datetime import datetime

from sqlalchemy import inspect, text

from crypto_store import EncryptedText, encrypt_text, is_encrypted, load_json, lookup_hash, save_json, decrypt_text
from database import Base, engine
import models  # noqa: F401  (registers the tables)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
BACKUP_FILE = os.path.join(OUTPUT_DIR, "db_backup_before_encryption.json")
ID_DB = os.path.join(PROJECT_ROOT, "src", "player_identifications.db")

JSON_STORES = (
    "assessments.json", "alert_reads.json", "injury_history.json", "player_accounts.json",
    "ai_injury.json", "ai_treatment.json", "detection_settings.json", "app_settings.json",
    "detector_status.json", "detector_status_backup.json",
)


def q(name):
    return '"' + name.replace('"', '""') + '"'


def encrypted_columns(table, db_columns=None):
    """{column name: column type} for the encrypted columns of a model table, plus any old text
    column left in the database that the models no longer use (e.g. teams.coach)."""
    out = {c.name: c.type for c in table.columns if isinstance(c.type, EncryptedText)}
    known = {c.name for c in table.columns}
    for name, info in (db_columns or {}).items():
        if name not in known and any(s in str(info["type"]).upper() for s in ("CHAR", "TEXT")):
            out[name] = EncryptedText()
    return out


def main():
    encrypt_text("check")      # fails early with a clear message when the key is missing

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    # brand-new database: create_all builds the encrypted schema directly
    Base.metadata.create_all(bind=engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in existing_tables])

    tables = [t for t in Base.metadata.sorted_tables if t.name in existing_tables]

    with engine.begin() as conn:

        # ---- 1. read everything (typed values, before any change) ----
        snapshot = {}
        for t in tables:
            rows = conn.execute(text("SELECT * FROM " + q(t.name))).mappings().all()
            snapshot[t.name] = [dict(r) for r in rows]

        # never overwrite the first backup (it holds the data from before encryption)
        backup = BACKUP_FILE
        if os.path.exists(backup):
            backup = BACKUP_FILE.replace(".json", "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
        save_json(backup, snapshot)
        db_cols = {t.name: {c["name"]: c for c in insp.get_columns(t.name)} for t in tables}
        print("[1/3] Backup (encrypted) saved:", backup, "|",
              ", ".join(f"{k}: {len(v)}" for k, v in snapshot.items()))

        # ---- 2a. schema: data and link columns -> TEXT, add missing ones ----
        # links (team_id, player_id, match_session_id ...) are encrypted too, so the database
        # foreign-key constraints are removed (the app checks the links itself)
        for t in tables:
            for (conname,) in conn.execute(text(
                "SELECT conname FROM pg_constraint WHERE conrelid = CAST(:t AS regclass) AND contype = 'f'"
            ), {"t": t.name}).all():
                conn.execute(text(f"ALTER TABLE {q(t.name)} DROP CONSTRAINT {q(conname)}"))

        for t in tables:
            cols = db_cols[t.name]
            for name in encrypted_columns(t, cols):
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE {q(t.name)} ADD COLUMN {q(name)} TEXT"))
                    continue
                conn.execute(text(f"ALTER TABLE {q(t.name)} ALTER COLUMN {q(name)} DROP DEFAULT"))
                if str(cols[name]["type"]).upper() != "TEXT":
                    conn.execute(text(f"ALTER TABLE {q(t.name)} ALTER COLUMN {q(name)} TYPE TEXT USING {q(name)}::text"))

        if "injury_events" in existing_tables:
            conn.execute(text("ALTER TABLE injury_events ALTER COLUMN player_id DROP NOT NULL"))

        if "users" in existing_tables:
            # the unique rule moves from username (now random-looking) to username_lookup
            for (conname,) in conn.execute(text(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'users'::regclass AND contype = 'u' "
                "AND pg_get_constraintdef(oid) ILIKE '%(username)%'"
            )).all():
                conn.execute(text("ALTER TABLE users DROP CONSTRAINT " + q(conname)))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS username_lookup VARCHAR(64)"))

        # ---- 2b. encrypt every value ----
        changed = 0
        for t in tables:
            enc_cols = encrypted_columns(t, db_cols[t.name])
            for row in snapshot[t.name]:
                values = {}
                for name, col_type in enc_cols.items():
                    v = row.get(name)
                    if v is None or is_encrypted(v):
                        continue
                    values[name] = encrypt_text(col_type._to_text(v))
                if t.name == "users":
                    values["username_lookup"] = lookup_hash(decrypt_text(row["username"]))
                if values:
                    sets = ", ".join(f"{q(k)} = :{k}" for k in values)
                    conn.execute(text(f"UPDATE {q(t.name)} SET {sets} WHERE id = :_id"), dict(values, _id=row["id"]))
                    changed += 1

        if "users" in existing_tables:
            conn.execute(text("ALTER TABLE users ALTER COLUMN username_lookup SET NOT NULL"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username_lookup ON users (username_lookup)"))

        print("[2/3] Database encrypted:", changed, "row(s) updated")

    # ---- 3. JSON stores + identification log ----
    done = []
    for name in JSON_STORES:
        path = os.path.join(OUTPUT_DIR, name)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            already = is_encrypted(f.read().strip())
        if already:
            continue
        data = load_json(path, None)
        if data is None:
            print("      skipped (not valid JSON):", name)
            continue
        save_json(path, data)
        done.append(name)

    id_rows = 0
    if os.path.isfile(ID_DB):
        con = sqlite3.connect(ID_DB)
        try:
            for rid, pname, detail in con.execute("SELECT id, player_name, detail FROM identifications").fetchall():
                new = (pname if pname is None or is_encrypted(pname) else encrypt_text(pname),
                       detail if detail is None or is_encrypted(detail) else encrypt_text(detail))
                if new != (pname, detail):
                    con.execute("UPDATE identifications SET player_name = ?, detail = ? WHERE id = ?", (*new, rid))
                    id_rows += 1
            con.commit()
        except sqlite3.Error as e:
            print("      identification log skipped:", e)
        finally:
            con.close()

    print("[3/3] JSON files encrypted:", ", ".join(done) or "none needed", "| identification log rows:", id_rows)
    print("Done. Start the backend again (uvicorn main:app --reload).")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FAILED:", e)
        print("The database step is all-or-nothing: if it did not print [2/3], the database was not changed.")
        sys.exit(1)
