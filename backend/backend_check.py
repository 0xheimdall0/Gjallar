from app.db import connect, init_db, utc_now

init_db()
conn = connect()

print("utc_now():   ", utc_now())
print("foreign_keys:", conn.execute("PRAGMA foreign_keys").fetchone()[0])
print("journal_mode:", conn.execute("PRAGMA journal_mode").fetchone()[0])

tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
)]
print("tables:      ", tables)

conn.close()
