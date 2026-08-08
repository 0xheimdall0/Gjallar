import sqlite3
import sys

from app.db import connect, init_db, utc_now
from app.auth import generate_token, hash_token, TOKEN_PREFIX_LENGTH

def create_source(name: str, description: str | None = None) -> None:
    init_db()
    conn = connect()
    token = generate_token()

    try:
        conn.execute(
            "INSERT INTO sources (name, token_prefix, token_hash, description, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (name, token[:TOKEN_PREFIX_LENGTH], hash_token(token), description, utc_now())
        )
        conn.commit()
    except sqlite3.IntegrityError:
        print("The given name is already taken.")
        sys.exit(1)

    print(f"\nSource '{name}' created.\n")
    print(f"   {token}\n")
    print("This token is shown ONCE and cannot be recovered. Store it now, preferably offline.")
    print("If you lose it, revoke the source and create a new one.")

    conn.close()

def list_sources() -> None:
    conn = connect()
    rows = conn.execute(
        "SELECT name, token_prefix, created_at, last_seen_at, revoked_at FROM sources ORDER BY name"
    ).fetchall()
    for r in rows:
        status = "revoked" if r["revoked_at"] else "active"
        print(f"{r['name']:20} {r['token_prefix']}... {status:8} last seen: {r['last_seen_at'] or 'never'}")
    conn.close()

def revoke_source(name: str) -> None:
    conn = connect()
    cursor = conn.execute(
        "UPDATE sources set revoked_at = ? WHERE name = ? AND revoked_at IS NULL", (utc_now(), name)
    )
    conn.commit()
    if cursor.rowcount > 0:
        print(f"{cursor.rowcount} row(s) modified.")
    else:
        print(f"No row has been found with name {name}.")
    conn.close()

if __name__ == "__main__":
    match sys.argv[1:]:
        case ["create-source", name]:          create_source(name)
        case ["create-source", name, desc]:    create_source(name, desc)
        case ["list-sources"]:                  list_sources()
        case ["revoke-source", name]:           revoke_source(name)
        case _:
            print(__doc__)
            sys.exit(1)