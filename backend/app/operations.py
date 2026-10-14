"""Durable monitor schedules, alert inbox/outbox, and operational audit records."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

from .auth import audit
from .models import ScheduleCreate
from .store import now


def later(seconds, current=None):
    return ((current or datetime.now(timezone.utc)) + timedelta(seconds=seconds)).isoformat()


class OperationError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Operations:
    def __init__(self, store, email_enabled=False, min_severity="high"):
        self.store = store
        self.email_enabled = email_enabled
        self.min_severity = min_severity
        with store.connection() as conn:
            conn.executescript("""
              CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL, enabled INTEGER NOT NULL, next_run TEXT NOT NULL,
                last_run TEXT, last_status TEXT NOT NULL DEFAULT 'never', last_error TEXT,
                failures INTEGER NOT NULL DEFAULT 0, lease_until TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS monitor_runs (
                id TEXT PRIMARY KEY, schedule_id TEXT NOT NULL, started_at TEXT NOT NULL,
                finished_at TEXT, status TEXT NOT NULL, scan_id TEXT, error TEXT
              );
              CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY, dedup_key TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL,
                kind TEXT NOT NULL, severity TEXT NOT NULL, title TEXT NOT NULL, source TEXT NOT NULL,
                scan_id TEXT, finding_id TEXT, schedule_id TEXT, detail TEXT NOT NULL,
                acknowledged_at TEXT, acknowledged_by TEXT, delivery TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, next_delivery TEXT, delivery_error TEXT
              );
              CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, actor TEXT NOT NULL,
                action TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL
              );
              CREATE INDEX IF NOT EXISTS schedules_due ON schedules(enabled, next_run);
              CREATE INDEX IF NOT EXISTS alerts_delivery ON alerts(delivery, next_delivery);
            """)

    def delivery_for(self, severity):
        ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return "pending" if self.email_enabled and ranks.get(severity, 3) <= ranks.get(self.min_severity, 1) else "inbox_only"

    def insert_alert(self, conn, key, kind, severity, title, source, detail, scan_id=None, finding_id=None, schedule_id=None):
        delivery = self.delivery_for(severity)
        conn.execute("INSERT OR IGNORE INTO alerts (id,dedup_key,created_at,kind,severity,title,source,scan_id,finding_id,schedule_id,detail,delivery,next_delivery) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (str(uuid4()), key, now(), kind, severity, title, source,
                        scan_id, finding_id, schedule_id, json.dumps(detail), delivery, now() if delivery == "pending" else None))

    def snapshot(self, conn, snapshot, actor="system", origin="manual"):
        for finding in snapshot["findings"]:
            disposition = conn.execute("SELECT status FROM dispositions WHERE finding_id=?", (finding["id"],)).fetchone()
            if disposition and disposition[0] == "resolved":
                continue
            identity = f"{snapshot['source']}:{finding['provider']}:{finding['account']}:{finding['id']}"
            key = "finding:" + hashlib.sha256(identity.encode()).hexdigest()
            self.insert_alert(conn, key, "finding", finding["severity"], finding["title"], snapshot["source"],
                {"provider": finding["provider"], "account": finding["account"], "resource": finding["resource_name"],
                 "method": finding.get("detection_method", "rule"), "rule_id": finding["rule_id"]}, snapshot["id"], finding["id"])
        if (snapshot.get("collection") or {}).get("partial"):
            coverage = snapshot["collection"]["coverage"]
            failed = [c["scope"] for c in coverage if c["status"] != "collected"]
            key = "coverage:" + hashlib.sha256(f"{snapshot['collection'].get('account')}:{snapshot['collection'].get('provider')}:{sorted(failed)}".encode()).hexdigest()
            self.insert_alert(conn, key, "coverage", "medium", "Cloud collection has incomplete coverage", snapshot["source"],
                              {"unavailable_scopes": failed}, snapshot["id"])
        audit(conn, actor, "scan.completed", snapshot["id"], {"source": snapshot["source"], "origin": origin,
                                                               "findings": len(snapshot["findings"])})

    def list_schedules(self):
        with self.store.connection() as conn:
            rows = conn.execute("SELECT * FROM schedules ORDER BY created_at DESC LIMIT 100").fetchall()
        return [dict(row) | {"enabled": bool(row["enabled"]), "collection": json.loads(row["payload"])} for row in rows]

    def create_schedule(self, body: ScheduleCreate, actor):
        schedule_id = str(uuid4())
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] >= 100:
                raise OperationError("This workspace already has 100 schedules.", 409)
            conn.execute("INSERT INTO schedules (id,name,kind,payload,interval_seconds,enabled,next_run,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (schedule_id, body.name, body.kind, body.collection.model_dump_json() if body.collection else "null",
                 body.interval_seconds, int(body.enabled), later(body.interval_seconds), actor, now()))
            audit(conn, actor, "schedule.created", schedule_id, {"kind": body.kind, "interval_seconds": body.interval_seconds})
        return next(s for s in self.list_schedules() if s["id"] == schedule_id)

    def update_schedule(self, schedule_id, body, actor):
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()
            if not row:
                raise OperationError("Schedule not found.", 404)
            if row["lease_until"] and row["lease_until"] > now():
                raise OperationError("This schedule is running. Wait for it to finish before editing.", 409)
            enabled = body.enabled if body.enabled is not None else bool(row["enabled"])
            interval = body.interval_seconds if body.interval_seconds is not None else row["interval_seconds"]
            conn.execute("UPDATE schedules SET enabled=?,interval_seconds=?,next_run=? WHERE id=?",
                         (int(enabled), interval, later(interval), schedule_id))
            audit(conn, actor, "schedule.updated", schedule_id, {"enabled": enabled, "interval_seconds": interval})
        return next(s for s in self.list_schedules() if s["id"] == schedule_id)

    def claim_schedule(self, schedule_id=None, current=None):
        current = current or datetime.now(timezone.utc)
        timestamp = current.isoformat()
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if schedule_id:
                row = conn.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()
                if row is None:
                    raise OperationError("Schedule not found.", 404)
                if row["lease_until"] and row["lease_until"] > timestamp:
                    raise OperationError("Schedule is already running.", 409)
            else:
                row = conn.execute("SELECT * FROM schedules WHERE enabled=1 AND next_run<=? AND (lease_until IS NULL OR lease_until<=?) ORDER BY next_run LIMIT 1", (timestamp, timestamp)).fetchone()
            if row is None:
                return None
            run_id = str(uuid4())
            conn.execute("UPDATE schedules SET lease_until=?, last_status='running' WHERE id=?", (later(300, current), row["id"]))
            conn.execute("INSERT INTO monitor_runs VALUES (?,?,?,NULL,'running',NULL,NULL)", (run_id, row["id"], timestamp))
            return dict(row) | {"run_id": run_id, "collection": json.loads(row["payload"])}

    def finish_schedule(self, claim, scan_id=None, error=None, busy=False, actor="scheduler"):
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM schedules WHERE id=?", (claim["id"],)).fetchone()
            failures = row["failures"] if busy else row["failures"] + 1 if error else 0
            status = "deferred" if busy else "failed" if error else "succeeded"
            delay = 10 if busy else min(3600, 60 * 2 ** min(failures - 1, 6)) if error else row["interval_seconds"]
            conn.execute("UPDATE schedules SET lease_until=NULL,last_run=?,last_status=?,last_error=?,failures=?,next_run=? WHERE id=?",
                         (now(), status, error, failures, later(delay), claim["id"]))
            conn.execute("UPDATE monitor_runs SET finished_at=?,status=?,scan_id=?,error=? WHERE id=?", (now(), status, scan_id, error, claim["run_id"]))
            if error and not busy:
                success = conn.execute("SELECT id FROM monitor_runs WHERE schedule_id=? AND status='succeeded' ORDER BY started_at DESC LIMIT 1", (claim["id"],)).fetchone()
                episode = success[0] if success else "initial"
                self.insert_alert(conn, f"schedule-failure:{claim['id']}:{episode}", "monitor_failure", "high",
                                  "Scheduled monitoring could not complete", "live" if row["kind"] == "live" else "demo",
                                  {"schedule": row["name"], "message": error}, schedule_id=claim["id"])
            audit(conn, actor, "schedule." + status, claim["id"], {"run_id": claim["run_id"], "scan_id": scan_id})

    def recover_interrupted(self):
        # Called only after acquiring the exclusive process lock for this database.
        with self.store.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM schedules WHERE last_status='running'").fetchone()[0]
            conn.execute("UPDATE schedules SET lease_until=NULL,last_status='interrupted',last_error='Previous process stopped before completion',next_run=? WHERE last_status='running'", (later(10),))
            conn.execute("UPDATE monitor_runs SET status='interrupted',finished_at=?,error='Previous process stopped before completion' WHERE status='running'", (now(),))
            conn.execute("UPDATE alerts SET delivery=CASE WHEN attempts>=5 THEN 'failed' ELSE 'pending' END,next_delivery=?,delivery_error='Delivery was interrupted; review its status' WHERE delivery='sending'", (now(),))
            if count:
                audit(conn, "scheduler", "monitor.recovered", detail={"interrupted": count})

    def list_runs(self):
        with self.store.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM monitor_runs ORDER BY started_at DESC LIMIT 100")]

    def list_alerts(self, limit=200, offset=0):
        with self.store.connection() as conn:
            rows = conn.execute("SELECT * FROM alerts ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            unread = conn.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged_at IS NULL").fetchone()[0]
        return {"items": [dict(row) | {"detail": json.loads(row["detail"])} for row in rows], "total": total, "unread": unread}

    def retry_delivery(self, alert_id, actor):
        if not self.email_enabled:
            raise OperationError("Email delivery is not configured on this server.", 409)
        with self.store.connection() as conn:
            row = conn.execute("SELECT delivery FROM alerts WHERE id=?", (alert_id,)).fetchone()
            if row is None:
                raise OperationError("Alert not found.", 404)
            if row[0] != "failed":
                raise OperationError("Only failed email deliveries can be retried manually.", 409)
            conn.execute("UPDATE alerts SET delivery='pending',attempts=0,next_delivery=?,delivery_error=NULL WHERE id=?", (now(), alert_id))
            audit(conn, actor, "alert.delivery.retried", alert_id)

    def acknowledge(self, alert_id, actor):
        with self.store.connection() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
            if not row:
                raise OperationError("Alert not found.", 404)
            conn.execute("UPDATE alerts SET acknowledged_at=COALESCE(acknowledged_at,?), acknowledged_by=COALESCE(acknowledged_by,?) WHERE id=?", (now(), actor, alert_id))
            audit(conn, actor, "alert.acknowledged", alert_id)

    def claim_delivery(self, current=None):
        timestamp = (current or datetime.now(timezone.utc)).isoformat()
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE alerts SET delivery='failed',delivery_error='Retry limit reached after interrupted delivery' WHERE delivery='sending' AND attempts>=5 AND next_delivery<=?", (timestamp,))
            row = conn.execute("SELECT * FROM alerts WHERE attempts<5 AND ((delivery='pending' AND next_delivery<=?) OR (delivery='sending' AND next_delivery<=?)) ORDER BY created_at LIMIT 1", (timestamp, timestamp)).fetchone()
            if not row:
                return None
            conn.execute("UPDATE alerts SET delivery='sending', attempts=attempts+1,next_delivery=? WHERE id=?", (later(300, current), row["id"]))
            return dict(row) | {"attempts": row["attempts"] + 1, "detail": json.loads(row["detail"])}

    def finish_delivery(self, alert, succeeded):
        state = "sent" if succeeded else "failed" if alert["attempts"] >= 5 else "pending"
        with self.store.connection() as conn:
            conn.execute("UPDATE alerts SET delivery=?,next_delivery=?,delivery_error=? WHERE id=?",
                         (state, None if state in ("sent", "failed") else later(min(3600, 60 * 2 ** (alert["attempts"] - 1))),
                          None if succeeded else "Email delivery failed; review the server's SMTP configuration.", alert["id"]))
            audit(conn, "notification-worker", "alert.delivery." + state, alert["id"])

    def audit_records(self):
        with self.store.connection() as conn:
            return [dict(row) | {"detail": json.loads(row["detail"])} for row in conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200")]
