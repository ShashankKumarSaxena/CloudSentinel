"""Atomic SQLite snapshots and separate, auditable finding dispositions."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .models import Inventory
from .rules import scan_resources
from .activity import aggregate


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.name in ('.runtime', 'cloudsentinel'):
            self.path.parent.chmod(0o700)
        with self.connection() as conn:
            conn.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, source TEXT NOT NULL,
                name TEXT NOT NULL, duration_ms REAL NOT NULL, snapshot TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS dispositions (
                finding_id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL
              );
              CREATE TABLE IF NOT EXISTS triage_events (
                id INTEGER PRIMARY KEY, finding_id TEXT NOT NULL,
                previous_status TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
              );
            """)
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def scan(self, inventory: Inventory, source: str, model=None, collection=None, phase=None, on_snapshot=None) -> dict:
        import time
        started = time.perf_counter()
        result = scan_resources(inventory.resources)
        for finding in result["findings"]:
            finding["detection_method"] = "rule"
        result["phase"] = phase or (2 if model is not None else 1)
        result["activity"] = {"event_count": len(inventory.events), "windows": [], "model": None}
        if model is not None:
            windows, anomalies, metadata = model.score(aggregate(inventory.events))
            result["findings"].extend(anomalies)
            result["activity"] = {"event_count": len(inventory.events), "windows": windows, "model": metadata}
            result["summary"]["anomalies"] = len(anomalies)
            result["summary"]["findings"] = len(result["findings"])
        result["collection"] = collection
        result["resources"] = [r.model_dump() for r in inventory.resources]
        result["schema_version"] = inventory.schema_version
        scan = {"id": str(uuid4()), "created_at": now(), "source": source,
                "name": inventory.name, "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
        with self.connection() as conn:
            conn.execute("INSERT INTO scans (id, created_at, source, name, duration_ms, snapshot) VALUES (?, ?, ?, ?, ?, ?)",
                         (scan["id"], scan["created_at"], scan["source"], scan["name"], scan["duration_ms"], json.dumps(result)))
            if on_snapshot:
                on_snapshot(conn, scan | result)
        return self.get_scan(scan["id"])

    def list_scans(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM scans ORDER BY rowid DESC LIMIT 100").fetchall()
        return [{k: row[k] for k in ("id", "created_at", "source", "name", "duration_ms")}
                | {"summary": json.loads(row["snapshot"])["summary"], "phase": json.loads(row["snapshot"]).get("phase", 1)} for row in rows]

    def get_scan(self, scan_id: str | None = None) -> dict | None:
        with self.connection() as conn:
            row = (conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone() if scan_id
                   else conn.execute("SELECT * FROM scans ORDER BY rowid DESC LIMIT 1").fetchone())
            dispositions = {r["finding_id"]: dict(r) for r in conn.execute("SELECT * FROM dispositions")}
        if row is None:
            return None
        result = json.loads(row["snapshot"])
        result.setdefault("phase", 1)
        result.setdefault("activity", {"event_count": 0, "windows": [], "model": None})
        result.setdefault("collection", None)
        for finding in result["findings"]:
            finding.setdefault("detection_method", "rule")
            disposition = dispositions.get(finding["id"], {})
            finding["status"] = disposition.get("status", "open")
            finding["updated_at"] = disposition.get("updated_at")
        return {k: row[k] for k in ("id", "created_at", "source", "name", "duration_ms")} | result

    def triage(self, finding_id: str, status: str) -> dict | None:
        scan = self.get_scan()
        finding = next((f for f in scan["findings"] if f["id"] == finding_id), None) if scan else None
        if finding is None:
            return None
        with self.connection() as conn:
            previous = conn.execute("SELECT status FROM dispositions WHERE finding_id = ?", (finding_id,)).fetchone()
            updated = now()
            conn.execute("INSERT INTO dispositions VALUES (?, ?, ?) ON CONFLICT(finding_id) "
                         "DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
                         (finding_id, status, updated))
            conn.execute("INSERT INTO triage_events (finding_id, previous_status, status, created_at) VALUES (?, ?, ?, ?)",
                         (finding_id, previous["status"] if previous else "open", status, updated))
        return finding | {"status": status, "updated_at": updated}

    def events(self, finding_id: str) -> list[dict]:
        with self.connection() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT previous_status, status, created_at FROM triage_events WHERE finding_id = ? ORDER BY id DESC",
                (finding_id,))]
