import contextlib
import secrets
import sqlite3

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from .db import utc_now

TOKEN_PREFIX_LENGTH = 12
TOKEN_LENGTH = 47

_hasher = PasswordHasher()

_DUMMY_HASH = _hasher.hash("dummy-token-for-constant-time-behavior")

def generate_token() -> str:
    token = f"sig_{secrets.token_urlsafe(32)}"
    return token

def hash_token(token: str) -> str:
    return _hasher.hash(token)

def verify_token(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    if len(token) != TOKEN_LENGTH:
        return None

    prefix = token[:TOKEN_PREFIX_LENGTH]
    row = conn.execute(
        "SELECT * FROM sources WHERE token_prefix = ? AND revoked_at IS NULL",
        (prefix,),
    ).fetchone()
    if row is None:
        # Burn the same CPU time as a real verification so that an unknown
        # prefix is indistinguishable from a wrong token. It always fails;
        # suppressing that is the point.
        with contextlib.suppress(VerificationError):
            _hasher.verify(_DUMMY_HASH, token)
        return None

    # A failure here means the token is wrong. It must NOT fall through —
    # suppressing this exception would authenticate anyone who knows the
    # (publicly stored) prefix.
    try:
        _hasher.verify(row["token_hash"], token)
    except (VerifyMismatchError, VerificationError):
        return None

    conn.execute("UPDATE sources SET last_seen_at = ? WHERE id = ?", (utc_now(), row["id"]))
    conn.commit()
    return row
