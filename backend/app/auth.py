import secrets
import sqlite3

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from .db import utc_now

TOKEN_PREFIX_LENGTH = 12

_hasher = PasswordHasher()

_DUMMY_HASH = _hasher.hash("dummy-token-for-constant-time-behavior")

def generate_token() -> str:
    token = f"sig_{secrets.token_urlsafe(32)}"
    return token

def hash_token(token: str) -> str:
    return _hasher.hash(token)

def verify_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    prefix = token[:TOKEN_PREFIX_LENGTH]
    row = conn.execute("SELECT * FROM sources WHERE token_prefix = ? AND revoked_at IS NULL", (prefix,)).fetchone()
    if row is None:
        try:
            _hasher.verify(_DUMMY_HASH, token)
        except Exception:
            pass
        return None

    try:
        _hasher.verify(row["token_hash"], token)
    except (VerifyMismatchError, VerificationError):
        return None

    conn.execute("UPDATE sources SET last_seen_at = ? WHERE id = ?", (utc_now(), row["id"]))
    conn.commit()
    return row