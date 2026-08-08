PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    token_prefix    TEXT NOT NULL UNIQUE,
    token_hash      TEXT NOT NULL,
    description     TEXT,
    created_at      TEXT NOT NULL,
    last_seen_at    TEXT,
    revoked_at      TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    message         TEXT,
    severity        TEXT NOT NULL CHECK (severity IN ('debug', 'info', 'warn', 'error', 'critical')),
    tags            TEXT NOT NULL DEFAULT '[]',
    metadata        TEXT,
    link            TEXT,
    received_at     TEXT NOT NULL,
    read_at         TEXT
);

CREATE TABLE IF NOT EXISTS heartbeats (
    id                          INTEGER PRIMARY KEY,
    source_id                   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    name                        TEXT NOT NULL,
    expected_interval_seconds   INTEGER NOT NULL CHECK (expected_interval_seconds > 0),
    grace_seconds               INTEGER NOT NULL DEFAULT 300 CHECK (grace_seconds >= 0),
    last_ping_at                TEXT,
    state                       TEXT NOT NULL DEFAULT 'ok' CHECK (state IN ('ok', 'late', 'down')),
    alerted_at                  TEXT,
    paused                      INTEGER NOT NULL DEFAULT 0 CHECK (paused IN (0, 1)),
    created_at                  TEXT NOT NULL,
    UNIQUE (source_id, name)
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id              INTEGER PRIMARY KEY,
    endpoint        TEXT NOT NULL UNIQUE,
    p256dh          TEXT NOT NULL,
    auth            TEXT NOT NULL,
    label           TEXT,
    min_severity    TEXT NOT NULL DEFAULT 'warn' CHECK (min_severity IN ('debug', 'info', 'warn', 'error', 'critical')),
    created_at      TEXT NOT NULL,
    last_success_at TEXT,
    failure_count   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_events_received                 ON events (received_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_source_received          ON events (source_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_severity_received        ON events (severity, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_unread_events                   ON events (received_at DESC) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_unpaused_heartbeats             ON heartbeats (state) WHERE paused = 0;