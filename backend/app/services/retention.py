"""Explicit maintenance that preserves current snapshots and unfinished work."""

from datetime import datetime, timedelta, timezone

from backend.app.services.auth import audit


class Retention:
    def __init__(self, store):
        self.store = store

    def run(self, days=90, apply=False):
        if days < 30:
            raise ValueError("Retention must preserve at least 30 days of evidence.")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        predicates = {
            "scans": "created_at<? AND id NOT IN (SELECT scan_id FROM account_snapshots) AND id<>(SELECT id FROM scans ORDER BY created_at DESC,id DESC LIMIT 1)",
            "collection_jobs": "created_at<? AND status IN ('succeeded','failed','cancelled')",
            "monitor_runs": "started_at<? AND status<>'running'",
            "alerts": "created_at<? AND acknowledged_at IS NOT NULL AND delivery IN ('inbox_only','sent','failed')",
        }
        counts = {}
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for table, predicate in predicates.items():
                # Identifiers/predicates are fixed application constants. Only
                # the cutoff is a value, and it always remains a bound parameter.
                counts[table] = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {predicate}", (cutoff,)
                ).fetchone()[0]
                if apply:
                    conn.execute(f"DELETE FROM {table} WHERE {predicate}", (cutoff,))
            if apply:
                conn.execute(
                    "DELETE FROM sessions WHERE expires_at<?",
                    (datetime.now(timezone.utc).isoformat(),),
                )
                audit(
                    conn, "local-cli", "retention.applied", detail={"days": days, "deleted": counts}
                )
        return {"applied": apply, "cutoff": cutoff, "records": counts, "audit_log_retained": True}
