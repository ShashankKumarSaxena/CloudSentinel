"""Durable collection queue with idempotent submission and explicit recovery."""

from uuid import uuid4
import hashlib
import json

from backend.app.domain.schemas import CollectionRequest
from backend.app.repositories.store import now
from backend.app.services.auth import audit
from backend.app.services.operations import OperationError


class CollectionJobs:
    def __init__(self, store, connections, settings, operations=None):
        self.store, self.connections, self.settings = store, connections, settings
        self.owner = None
        self.operations = operations

    @staticmethod
    def public(row):
        return {
            key: row[key]
            for key in (
                "id",
                "created_at",
                "created_by",
                "status",
                "started_at",
                "finished_at",
                "scan_id",
                "error",
                "attempts",
            )
        } | {"request": json.loads(row["payload"])}

    def submit(self, body: CollectionRequest, actor: str, idempotency_key: str):
        # Revalidate account/region before both accepting and executing the job.
        if not self.settings.production and not self.settings.allow_live_in_demo:
            raise OperationError("Demo mode is offline; cloud collection is disabled.", 403)
        account, body = self.connections.resolve(body)
        payload = body.model_dump_json()
        fingerprint = hashlib.sha256((actor + ":" + idempotency_key).encode()).hexdigest()
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM collection_jobs WHERE idempotency_key=?", (fingerprint,)
            ).fetchone()
            if existing:
                if existing["payload"] != payload:
                    raise OperationError(
                        "An idempotency key cannot be reused for a different request.", 409
                    )
                return self.public(existing)
            count = conn.execute(
                "SELECT COUNT(*) FROM collection_jobs WHERE status IN ('pending','running')"
            ).fetchone()[0]
            if count >= self.settings.max_pending_jobs:
                raise OperationError(
                    "Collection queue is full. Retry after existing jobs complete.", 429
                )
            job_id = str(uuid4())
            conn.execute(
                "INSERT INTO collection_jobs (id,idempotency_key,created_at,created_by,payload,status) VALUES (?,?,?,?,?,'pending')",
                (job_id, fingerprint, now(), actor, payload),
            )
            audit(
                conn,
                actor,
                "collection.queued",
                job_id,
                {"connection_id": account.id, "region": body.region},
            )
            return self.public(
                conn.execute("SELECT * FROM collection_jobs WHERE id=?", (job_id,)).fetchone()
            )

    def get(self, job_id):
        with self.store.connection() as conn:
            row = conn.execute("SELECT * FROM collection_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise OperationError("Collection job not found.", 404)
        return self.public(row)

    def list(self, limit=100, offset=0):
        with self.store.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM collection_jobs ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM collection_jobs").fetchone()[0]
        return {"items": [self.public(row) for row in rows], "total": total}

    def cancel(self, job_id, actor):
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status FROM collection_jobs WHERE id=?", (job_id,)
            ).fetchone()
            if not row:
                raise OperationError("Collection job not found.", 404)
            if row["status"] != "pending":
                raise OperationError("Only pending collection jobs can be cancelled.", 409)
            conn.execute(
                "UPDATE collection_jobs SET status='cancelled',finished_at=? WHERE id=?",
                (now(), job_id),
            )
            audit(conn, actor, "collection.cancelled", job_id)

    def claim(self):
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._assert_owner_in(conn)
            row = conn.execute(
                "SELECT * FROM collection_jobs WHERE status='pending' ORDER BY created_at, id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE collection_jobs SET status='running',started_at=?,attempts=attempts+1 WHERE id=?",
                (now(), row["id"]),
            )
            return self.public(row)

    def finish(self, job_id, scan_id=None, busy=False):
        status = "pending" if busy else "succeeded" if scan_id else "failed"
        error = (
            None
            if scan_id or busy
            else "Collection failed. Review account identity, read permissions, and coverage configuration."
        )
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._assert_owner_in(conn)
            conn.execute(
                "UPDATE collection_jobs SET status=?,finished_at=?,scan_id=?,error=? WHERE id=?",
                (status, None if busy else now(), scan_id, error, job_id),
            )
            if status == "failed" and self.operations:
                self.operations.insert_alert(
                    conn,
                    "collection-failure:" + job_id,
                    "collection_failure",
                    "high",
                    "Cloud collection job could not complete",
                    "live",
                    {"job_id": job_id, "message": error},
                )
            audit(conn, "worker", "collection." + status, job_id, {"scan_id": scan_id})

    def recover(self):
        # Called only after acquiring the singleton database worker lock. Jobs
        # interrupted after a scan commit may rerun; immutable history remains
        # truthful and finding-alert fingerprints suppress duplicate inbox entries.
        with self.store.connection() as conn:
            conn.execute(
                "UPDATE collection_jobs SET status='pending',started_at=NULL,error='Previous worker stopped before completion' WHERE status='running' AND attempts<3"
            )
            conn.execute(
                "UPDATE collection_jobs SET status='failed',finished_at=?,error='Interrupted collection retry limit reached' WHERE status='running' AND attempts>=3",
                (now(),),
            )

    def begin_worker(self):
        """Acquire a fencing identity after the singleton process lock is held."""
        self.owner = str(uuid4())
        with self.store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO worker_heartbeat (id,updated_at,status,owner) VALUES (1,?,'running',?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,status=excluded.status,owner=excluded.owner",
                (now(), self.owner),
            )

    def heartbeat(self, status="running"):
        with self.store.connection() as conn:
            cursor = conn.execute(
                "UPDATE worker_heartbeat SET updated_at=?,status=? WHERE id=1 AND owner=?",
                (now(), status, self.owner),
            )
            if cursor.rowcount != 1:
                raise WorkerOwnershipLost("Worker ownership changed; restart this process.")

    def _assert_owner_in(self, conn):
        row = conn.execute("SELECT owner FROM worker_heartbeat WHERE id=1").fetchone()
        if not row or row[0] != self.owner:
            raise WorkerOwnershipLost("Worker ownership changed; restart this process.")

    def assert_owner(self):
        with self.store.connection() as conn:
            self._assert_owner_in(conn)

    def worker_status(self):
        with self.store.connection() as conn:
            row = conn.execute("SELECT * FROM worker_heartbeat WHERE id=1").fetchone()
        return dict(row) if row else None


class WorkerOwnershipLost(RuntimeError):
    """An obsolete worker must stop before it can publish results."""
