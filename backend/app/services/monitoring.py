"""Single-process periodic worker with durable leases and graceful shutdown."""

import threading

from backend.app.domain.schemas import CollectionRequest
from backend.app.repositories.store import now
from backend.app.services.jobs import WorkerOwnershipLost
from backend.app.services.operations import OperationError


class BusyOperation(Exception):
    pass


class MonitorWorker:
    def __init__(self, operations, engine, delivery, enabled=True, jobs=None):
        self.operations, self.engine, self.delivery = operations, engine, delivery
        self.enabled = enabled
        self.jobs = jobs
        self.stop_event = threading.Event()
        self.thread = None
        self.lock_file = None
        self.last_tick = None
        self.last_error = None

    def start(self):
        if not self.enabled:
            return
        self.lock_file = self.operations.store.database.lock_worker()
        try:
            if self.jobs:
                self.jobs.begin_worker()
                self.engine.worker_owner = self.jobs.owner
                self.jobs.recover()
                self.jobs.heartbeat()
            self.operations.recover_interrupted()
        except Exception:
            self.lock_file.close()
            self.lock_file = None
            raise
        self.thread = threading.Thread(target=self.run, name="cloudsentinel-monitor", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=130)

    def status(self):
        return {
            "enabled": self.enabled,
            "running": bool(self.thread and self.thread.is_alive()),
            "last_tick": self.last_tick,
            "last_error": self.last_error,
            "email_enabled": self.delivery.enabled,
        }

    def execute(self, claim, actor="scheduler"):
        try:
            if claim["kind"] == "demo":
                scan = self.engine.demo(actor=actor, origin="schedule:" + claim["id"])
            else:
                scan = self.engine.collect(
                    CollectionRequest.model_validate(claim["collection"]),
                    actor=actor,
                    origin="schedule:" + claim["id"],
                )
            self.operations.finish_schedule(
                claim,
                scan_id=scan["id"],
                actor=actor,
                worker_owner=self.jobs.owner if self.jobs else None,
            )
            return scan
        except BusyOperation:
            self.operations.finish_schedule(
                claim,
                error="Another scan or training operation is active.",
                busy=True,
                actor=actor,
                worker_owner=self.jobs.owner if self.jobs else None,
            )
            raise OperationError(
                "A scan or training operation is already active. This schedule will retry.", 409
            ) from None
        except WorkerOwnershipLost:
            raise
        except Exception:
            if self.jobs:
                self.jobs.assert_owner()
            self.operations.finish_schedule(
                claim,
                error="Collection or analysis failed. Review local credentials, permissions, and supported scope.",
                actor=actor,
                worker_owner=self.jobs.owner if self.jobs else None,
            )
            raise OperationError(
                "Scheduled collection or analysis could not complete. Review the run history.", 502
            ) from None

    def tick(self):
        if self.lock_file:
            try:
                self.lock_file.assert_owned()
            except Exception:
                raise WorkerOwnershipLost("Worker lock connection was lost.") from None
        if self.jobs:
            self.jobs.heartbeat()
            job = self.jobs.claim()
            if job:
                try:
                    scan = self.engine.collect(
                        CollectionRequest.model_validate(job["request"]),
                        actor=job["created_by"],
                        origin="job:" + job["id"],
                    )
                    self.jobs.finish(job["id"], scan_id=scan["id"])
                except BusyOperation:
                    self.jobs.finish(job["id"], busy=True)
                except Exception:
                    self.jobs.finish(job["id"])
                self.jobs.heartbeat()
        claim = self.operations.claim_schedule(worker_owner=self.jobs.owner if self.jobs else None)
        if claim:
            try:
                self.execute(claim)
            except OperationError:
                pass
        alert = self.operations.claim_delivery() if self.delivery.enabled else None
        if alert:
            self.operations.finish_delivery(alert, self.delivery.send(alert))
        self.last_tick = now()

    def run(self):
        consecutive_errors = 0
        try:
            while not self.stop_event.is_set():
                try:
                    self.tick()
                    self.last_error = None
                    consecutive_errors = 0
                except WorkerOwnershipLost:
                    self.last_error = "Worker ownership changed; the process is stopping."
                    self.stop_event.set()
                except Exception:
                    self.last_error = "Background processing encountered an error; review local storage and configuration."
                    consecutive_errors += 1
                    if consecutive_errors >= 5:
                        self.stop_event.set()
                self.stop_event.wait(2)
        finally:
            try:
                if self.jobs:
                    try:
                        self.jobs.heartbeat("stopped")
                    except Exception:
                        pass
            finally:
                if self.lock_file:
                    self.lock_file.close()
