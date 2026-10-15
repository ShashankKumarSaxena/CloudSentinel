CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    name TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    snapshot TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dispositions (
    finding_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS triage_events (
    id INTEGER PRIMARY KEY,
    finding_id TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    csrf TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    key TEXT PRIMARY KEY,
    failures INTEGER NOT NULL,
    window_start TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    detail TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL,
    enabled INTEGER NOT NULL,
    next_run TEXT NOT NULL,
    last_run TEXT,
    last_status TEXT NOT NULL DEFAULT 'never',
    last_error TEXT,
    failures INTEGER NOT NULL DEFAULT 0,
    lease_until TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monitor_runs (
    id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    scan_id TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    dedup_key TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    scan_id TEXT,
    finding_id TEXT,
    schedule_id TEXT,
    detail TEXT NOT NULL,
    acknowledged_at TEXT,
    acknowledged_by TEXT,
    delivery TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_delivery TEXT,
    delivery_error TEXT
);

CREATE INDEX IF NOT EXISTS schedules_due ON schedules(enabled, next_run);

CREATE INDEX IF NOT EXISTS alerts_delivery ON alerts(delivery, next_delivery);
