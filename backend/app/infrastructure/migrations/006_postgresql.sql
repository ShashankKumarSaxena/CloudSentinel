ALTER TABLE scans ADD COLUMN summary TEXT;
ALTER TABLE scans ADD COLUMN phase INTEGER NOT NULL DEFAULT 1;
UPDATE scans SET summary=(snapshot::jsonb->'summary')::text,phase=COALESCE((snapshot::jsonb->>'phase')::integer,1);
CREATE INDEX IF NOT EXISTS scans_created ON scans(created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS sessions_user_activity ON sessions(user_id,last_seen DESC);
CREATE INDEX IF NOT EXISTS triage_finding ON triage_events(finding_id,id DESC);
CREATE INDEX IF NOT EXISTS audit_actor ON audit_log(actor,id DESC);
CREATE INDEX IF NOT EXISTS audit_action ON audit_log(action,id DESC);
CREATE INDEX IF NOT EXISTS snapshot_scan ON account_snapshots(scan_id);
