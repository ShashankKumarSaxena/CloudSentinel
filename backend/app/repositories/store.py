"""Atomic database snapshots and separate, auditable finding dispositions."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json

from backend.app.domain.activity import aggregate
from backend.app.domain.rules import scan_resources
from backend.app.domain.schemas import Inventory


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path, database_url: str | None = None):
        from backend.app.infrastructure.database import Database

        self.path = path
        self.database = Database(path, database_url)

    def connection(self):
        return self.database.connection()

    def scan(
        self,
        inventory: Inventory,
        source: str,
        model=None,
        collection=None,
        phase=None,
        on_snapshot=None,
    ) -> dict:
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
            result["activity"] = {
                "event_count": len(inventory.events),
                "windows": windows,
                "model": metadata,
            }
            result["summary"]["anomalies"] = len(anomalies)
            result["summary"]["findings"] = len(result["findings"])
        result["analysis"] = {
            "ml_enabled": model is not None,
            "notice": (
                "Activity model scoring was performed."
                if model
                else "Activity ML scoring is disabled; configuration rules remain active."
            ),
        }
        result["collection"] = collection
        result["resources"] = [r.model_dump() for r in inventory.resources]
        result["schema_version"] = inventory.schema_version
        scan = {
            "id": str(uuid4()),
            "created_at": now(),
            "source": source,
            "name": inventory.name,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO scans (id, created_at, source, name, duration_ms, snapshot, summary, phase) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scan["id"],
                    scan["created_at"],
                    scan["source"],
                    scan["name"],
                    scan["duration_ms"],
                    json.dumps(result),
                    json.dumps(result["summary"]),
                    result["phase"],
                ),
            )
            if source == "live" and collection and collection.get("connection_id"):
                conn.execute(
                    "INSERT INTO account_snapshots VALUES (?,?,?,?) ON CONFLICT(connection_id,region) DO UPDATE SET scan_id=excluded.scan_id,updated_at=excluded.updated_at",
                    (
                        collection["connection_id"],
                        collection["region"],
                        scan["id"],
                        scan["created_at"],
                    ),
                )
            if on_snapshot:
                on_snapshot(conn, scan | result)
        return self.get_scan(scan["id"])

    def list_scans(self, limit=100, offset=0) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id,created_at,source,name,duration_ms,summary,phase, "
                "CASE WHEN summary IS NULL THEN snapshot ELSE NULL END AS legacy_snapshot "
                "FROM scans ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        records = []
        for row in rows:
            # Indexed metadata avoids loading 100 full resource/activity snapshots
            # just to render history. Raw legacy inserts remain readable.
            legacy = json.loads(row["legacy_snapshot"]) if row["legacy_snapshot"] else None
            records.append(
                {key: row[key] for key in ("id", "created_at", "source", "name", "duration_ms")}
                | {
                    "summary": json.loads(row["summary"]) if row["summary"] else legacy["summary"],
                    "phase": row["phase"] if row["summary"] else legacy.get("phase", 1),
                }
            )
        return records

    def get_scan(self, scan_id: str | None = None) -> dict | None:
        with self.connection() as conn:
            row = (
                conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
                if scan_id
                else conn.execute(
                    "SELECT * FROM scans ORDER BY created_at DESC, id DESC LIMIT 1"
                ).fetchone()
            )
            if row is None:
                return None
            result = json.loads(row["snapshot"])
            # Read dispositions for this snapshot only. A large organization can
            # retain many historical finding IDs unrelated to the selected account.
            finding_ids = [finding["id"] for finding in result["findings"]]
            dispositions = {}
            for offset in range(0, len(finding_ids), 500):
                batch = finding_ids[offset : offset + 500]
                placeholders = ",".join("?" for _ in batch)
                records = conn.execute(
                    f"SELECT * FROM dispositions WHERE finding_id IN ({placeholders})", batch
                ).fetchall()
                dispositions.update({record["finding_id"]: dict(record) for record in records})
        result.setdefault("phase", 1)
        result.setdefault("activity", {"event_count": 0, "windows": [], "model": None})
        result.setdefault("collection", None)
        for finding in result["findings"]:
            finding.setdefault("detection_method", "rule")
            disposition = dispositions.get(finding["id"], {})
            finding["status"] = disposition.get("status", "open")
            finding["updated_at"] = disposition.get("updated_at")
        return {k: row[k] for k in ("id", "created_at", "source", "name", "duration_ms")} | result

    def triage(
        self, finding_id: str, status: str, scan_id: str | None = None, on_change=None
    ) -> dict | None:
        with self.connection() as conn:
            # Use the same short write-serialization boundary as snapshot commits,
            # so a current-account check cannot race a newer collection pointer.
            conn.execute("BEGIN IMMEDIATE")
            scan = self.get_scan(scan_id)
            if scan_id and not self.is_current(scan):
                return None
            finding = (
                next((item for item in scan["findings"] if item["id"] == finding_id), None)
                if scan
                else None
            )
            if finding is None:
                return None
            previous = conn.execute(
                "SELECT status FROM dispositions WHERE finding_id = ?", (finding_id,)
            ).fetchone()
            updated = now()
            conn.execute(
                "INSERT INTO dispositions VALUES (?, ?, ?) ON CONFLICT(finding_id) "
                "DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
                (finding_id, status, updated),
            )
            conn.execute(
                "INSERT INTO triage_events (finding_id, previous_status, status, created_at) VALUES (?, ?, ?, ?)",
                (finding_id, previous["status"] if previous else "open", status, updated),
            )
            if on_change:
                on_change(conn, finding | {"status": status, "updated_at": updated})
        return finding | {"status": status, "updated_at": updated}

    def events(self, finding_id: str) -> list[dict]:
        with self.connection() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT previous_status, status, created_at FROM triage_events WHERE finding_id = ? ORDER BY id DESC",
                    (finding_id,),
                )
            ]

    def is_current(self, scan):
        if not scan:
            return False
        collection = scan.get("collection") or {}
        if collection.get("connection_id"):
            with self.connection() as conn:
                row = conn.execute(
                    "SELECT scan_id FROM account_snapshots WHERE connection_id=? AND region=?",
                    (collection["connection_id"], collection["region"]),
                ).fetchone()
            return row is not None and row[0] == scan["id"]
        latest = self.get_scan()
        return latest is not None and latest["id"] == scan["id"]

    def account_snapshots(self):
        with self.connection() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM account_snapshots ORDER BY connection_id,region"
                )
            ]
