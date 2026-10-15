CREATE TABLE IF NOT EXISTS account_snapshots (
    connection_id TEXT NOT NULL,
    region TEXT NOT NULL,
    scan_id TEXT NOT NULL REFERENCES scans(id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (connection_id, region)
);
