"""Single-process periodic worker with durable leases and graceful shutdown."""
import fcntl
import threading
from pathlib import Path

from .models import CollectionRequest
from .operations import OperationError
from .store import now


class BusyOperation(Exception):
    pass


class MonitorWorker:
    def __init__(self, operations, engine, delivery, enabled=True):
        self.operations, self.engine, self.delivery = operations, engine, delivery
        self.enabled = enabled
        self.stop_event = threading.Event()
        self.thread = None
        self.lock_file = None
        self.last_tick = None
        self.last_error = None

    def start(self):
        if not self.enabled:
            return
        path = self.operations.store.path.parent / (self.operations.store.path.name + ".monitor.lock")
        self.lock_file = Path(path).open("a")
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock_file.close()
            self.lock_file = None
            raise RuntimeError("Another monitoring process owns this database. Run one server worker per database.") from None
        try:
            self.operations.recover_interrupted()
        except Exception:
            fcntl.flock(self.lock_file, fcntl.LOCK_UN)
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
        return {"enabled": self.enabled, "running": bool(self.thread and self.thread.is_alive()),
                "last_tick": self.last_tick, "last_error": self.last_error, "email_enabled": self.delivery.enabled}

    def execute(self, claim, actor="scheduler"):
        try:
            if claim["kind"] == "demo":
                scan = self.engine.demo(actor=actor, origin="schedule:" + claim["id"])
            else:
                scan = self.engine.collect(CollectionRequest.model_validate(claim["collection"]), actor=actor, origin="schedule:" + claim["id"])
            self.operations.finish_schedule(claim, scan_id=scan["id"], actor=actor)
            return scan
        except BusyOperation:
            self.operations.finish_schedule(claim, error="Another scan or training operation is active.", busy=True, actor=actor)
            raise OperationError("A scan or training operation is already active. This schedule will retry.", 409) from None
        except Exception:
            self.operations.finish_schedule(claim, error="Collection or analysis failed. Review local credentials, permissions, and supported scope.", actor=actor)
            raise OperationError("Scheduled collection or analysis could not complete. Review the run history.", 502) from None

    def tick(self):
        claim = self.operations.claim_schedule()
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
        try:
            while not self.stop_event.is_set():
                try:
                    self.tick()
                    self.last_error = None
                except Exception:
                    self.last_error = "Background processing encountered an error; review local storage and configuration."
                self.stop_event.wait(2)
        finally:
            if self.lock_file:
                fcntl.flock(self.lock_file, fcntl.LOCK_UN)
                self.lock_file.close()
