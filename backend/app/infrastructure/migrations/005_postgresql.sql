ALTER TABLE worker_heartbeat ADD COLUMN owner TEXT NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS finding_episodes (
    fingerprint TEXT PRIMARY KEY,
    episode INTEGER NOT NULL,
    active INTEGER NOT NULL
);
