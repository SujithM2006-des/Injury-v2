"""
crypto_store.py - encryption for everything AthleteGuard stores.

  - Database columns: AES-256-GCM through the SQLAlchemy column types below
    (EncryptedText / EncryptedInt / EncryptedFloat / EncryptedBool / EncryptedDateTime).
    Values are encrypted when written and decrypted when read, so the rest of the code
    works with normal Python values. IDs and foreign keys stay plain so tables can join.
  - JSON files in output/: save_json() / load_json() encrypt the whole file.
  - Usernames: lookup_hash() gives a keyed hash, so a login can be found without
    decrypting every row.
  - API responses: session_key() gives the per-login key the frontend decrypts with
    (see secure_transport.py).

The master key is ATHLETEGUARD_DATA_KEY in .env (project root, src/.env or backend/.env).
Create one with:   python crypto_store.py --new-key
Lose the key = lose the data. Keep a copy somewhere safe.

The same file is in backend/ and src/ (like database.py and models.py) - keep them identical.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.types import Text, TypeDecorator

KEY_NAME = "ATHLETEGUARD_DATA_KEY"
PREFIX = "enc1:"

_HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_HERE)
ENV_FILES = [
    os.path.join(PROJECT_ROOT, ".env"),
    os.path.join(PROJECT_ROOT, "src", ".env"),
    os.path.join(PROJECT_ROOT, "backend", ".env"),
]


# ============================================
# KEY
# ============================================

def _read_env_key():
    if os.environ.get(KEY_NAME):
        return os.environ[KEY_NAME].strip()
    for path in ENV_FILES:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    k, _, v = line.strip().partition("=")
                    if k.strip() == KEY_NAME and v.strip():
                        return v.strip().strip('"').strip("'")
        except OSError:
            pass
    return None


_keys = None


def _load_keys():
    global _keys
    if _keys is not None:
        return _keys
    raw = _read_env_key()
    if not raw:
        raise RuntimeError(
            KEY_NAME + " is not set. Create it once with:  python crypto_store.py --new-key  "
            "(then keep a copy of src/.env somewhere safe - without the key the data cannot be read)"
        )
    try:
        master = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except Exception:
        raise RuntimeError(KEY_NAME + " is not valid base64")
    if len(master) != 32:
        raise RuntimeError(KEY_NAME + " must be 32 bytes (use python crypto_store.py --new-key)")

    def derive(label):
        return hmac.new(master, label, hashlib.sha256).digest()

    _keys = {
        "data": AESGCM(derive(b"athleteguard-data-v1")),
        "lookup": derive(b"athleteguard-lookup-v1"),
        "session": derive(b"athleteguard-session-v1"),
    }
    return _keys


# ============================================
# ENCRYPT / DECRYPT
# Format: "enc1:" + base64(12-byte nonce + ciphertext + tag)
# ============================================

def encrypt_bytes(aes, data):
    nonce = secrets.token_bytes(12)
    return base64.b64encode(nonce + aes.encrypt(nonce, data, None)).decode("ascii")


def decrypt_bytes(aes, text):
    raw = base64.b64decode(text)
    return aes.decrypt(raw[:12], raw[12:], None)


def is_encrypted(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt_text(value):
    if value is None:
        return None
    return PREFIX + encrypt_bytes(_load_keys()["data"], str(value).encode("utf-8"))


def decrypt_text(value):
    """Plain (not yet encrypted) values are returned as they are."""
    if value is None or not is_encrypted(value):
        return value
    return decrypt_bytes(_load_keys()["data"], value[len(PREFIX):]).decode("utf-8")


def lookup_hash(value):
    """Keyed hash used to find a row (e.g. a username) without decrypting every row. Case-insensitive."""
    text = str(value or "").strip().lower()
    return hmac.new(_load_keys()["lookup"], text.encode("utf-8"), hashlib.sha256).hexdigest()


def session_key(sid):
    """32-byte AES key for one login session (sid comes from the login token)."""
    return hmac.new(_load_keys()["session"], str(sid).encode("utf-8"), hashlib.sha256).digest()


def now_utc():
    return datetime.now(timezone.utc)


# ============================================
# DATABASE COLUMN TYPES (stored as TEXT)
# ============================================

class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_text(self._to_text(value)) if value is not None else None

    def process_result_value(self, value, dialect):
        return self._from_text(decrypt_text(value)) if value is not None else None

    def _to_text(self, value):
        return str(value)

    def _from_text(self, text):
        return text


class EncryptedInt(EncryptedText):
    cache_ok = True

    def _to_text(self, value):
        return str(int(value))

    def _from_text(self, text):
        return int(float(text))


class EncryptedFloat(EncryptedText):
    cache_ok = True

    def _to_text(self, value):
        return repr(float(value))

    def _from_text(self, text):
        return float(text)


class EncryptedBool(EncryptedText):
    cache_ok = True

    def _to_text(self, value):
        return "1" if value else "0"

    def _from_text(self, text):
        return str(text).strip().lower() in ("1", "true", "t", "yes")


class EncryptedDateTime(EncryptedText):
    cache_ok = True

    def _to_text(self, value):
        if isinstance(value, str):
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()

    def _from_text(self, text):
        text = str(text).strip().replace(" ", "T", 1)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        if len(text) > 3 and text[-3] in "+-" and text[-6] not in "+-":
            text += ":00"          # "+00" -> "+00:00" (Postgres text form)
        value = datetime.fromisoformat(text)
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ============================================
# JSON FILES
# ============================================

def dumps_encrypted(data):
    return encrypt_text(json.dumps(data, default=str, ensure_ascii=False))


def loads_maybe_encrypted(text):
    text = text.strip()
    return json.loads(decrypt_text(text) if is_encrypted(text) else text)


def load_json(path, default):
    """Reads an encrypted (or older plain) JSON file. Missing / unreadable -> default."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return loads_maybe_encrypted(f.read())
    except (OSError, ValueError):
        return default


def save_json(path, data):
    """Writes the JSON file encrypted (atomic replace). Raises OSError on failure."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(dumps_encrypted(data))
    os.replace(tmp, path)


# ============================================
# COMMAND LINE
#   python crypto_store.py --new-key        create the key in src/.env (only if none exists)
#   python crypto_store.py --show <file>    print a decrypted JSON file from output/
# ============================================

if __name__ == "__main__":
    if "--new-key" in sys.argv:
        if _read_env_key():
            sys.exit(KEY_NAME + " already exists - nothing changed (a new key would make the data unreadable).")
        target = os.path.join(PROJECT_ROOT, "src", ".env")
        key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
        with open(target, "a", encoding="utf-8") as f:
            f.write("\n" + KEY_NAME + "=" + key + "\n")
        print("Key added to", target)
        print("Keep a copy of this file somewhere safe: without the key the data cannot be read.")
    elif "--show" in sys.argv and len(sys.argv) > sys.argv.index("--show") + 1:
        print(json.dumps(load_json(sys.argv[sys.argv.index("--show") + 1], None), indent=1, ensure_ascii=False))
    else:
        print(__doc__)
