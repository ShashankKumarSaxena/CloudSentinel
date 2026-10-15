"""Shared scan/training operations for requests and scheduled monitoring."""

import threading

from backend.app.core.config import Settings
from backend.app.core.paths import PROJECT_ROOT as ROOT
from backend.app.domain.schemas import Inventory, TrainingDataset
from backend.app.infrastructure.collectors import collect
from backend.app.infrastructure.credentials import collect_approved
from backend.app.services.auth import audit
from backend.app.services.monitoring import BusyOperation
from backend.app.services.operations import OperationError


class ScanEngine:
    def __init__(self, store, model, operations, settings=None, connections=None):
        self.store, self.model, self.operations = store, model, operations
        self.settings = settings or Settings()
        self.connections = connections
        self.lock = threading.Lock()
        self.worker_owner = None

    def _scan(self, inventory, source, actor, origin, collection=None):
        scoring_model = None
        if self.settings.mode == "demo" and source != "live":
            self.model.ensure_default()
            scoring_model = self.model
        elif self.settings.live_ml_enabled:
            metadata = self.model.status()
            if not metadata.get("ready") or metadata.get("provenance") != "user_labeled":
                raise OperationError(
                    "Live ML requires a reviewed non-synthetic model artifact.", 409
                )
            scoring_model = self.model
        result = self.store.scan(
            inventory,
            source,
            model=scoring_model,
            collection=collection,
            phase=3,
            on_snapshot=lambda conn, snapshot: self._record_snapshot(conn, snapshot, actor, origin),
        )
        return result

    def _record_snapshot(self, conn, snapshot, actor, origin):
        if self.worker_owner:
            row = conn.execute("SELECT owner FROM worker_heartbeat WHERE id=1").fetchone()
            if not row or row[0] != self.worker_owner:
                from backend.app.services.jobs import WorkerOwnershipLost

                raise WorkerOwnershipLost("An obsolete worker cannot publish a snapshot.")
        self.operations.snapshot(conn, snapshot, actor, origin)

    def demo(self, actor="system", origin="manual"):
        if self.settings.production:
            raise OperationError(
                "Synthetic scans are available only in the separate demo deployment.", 403
            )
        inventory = Inventory.model_validate_json(
            (ROOT / "data/demo_activity_inventory.json").read_text()
        )
        return self.scan(inventory, "demo", actor, origin)

    def scan(self, inventory, source, actor="system", origin="manual"):
        if not self.lock.acquire(blocking=False):
            raise BusyOperation()
        try:
            return self._scan(inventory, source, actor, origin)
        finally:
            self.lock.release()

    def collect(self, body, actor="system", origin="manual"):
        if not self.settings.production and not self.settings.allow_live_in_demo:
            raise OperationError(
                "Demo mode is offline. Use the production deployment for approved cloud accounts.",
                403,
            )
        if not self.lock.acquire(blocking=False):
            raise BusyOperation()
        try:
            if body.connection_id:
                account, body = self.connections.resolve(body)
                inventory, coverage = collect_approved(body, account)
                if any(
                    resource.provider != account.provider or resource.account != account.account
                    for resource in inventory.resources
                ) or any(
                    event.provider != account.provider or event.account != account.account
                    for event in inventory.events
                ):
                    raise OperationError(
                        "Collected inventory did not match the approved account scope.", 502
                    )
                coverage["connection_id"] = account.id
                coverage["region"] = body.region
            elif self.settings.production:
                raise OperationError(
                    "Production collection requires an approved cloud connection.", 403
                )
            else:
                inventory, coverage = collect(body)
            return self._scan(inventory, "live", actor, origin, coverage)
        finally:
            self.lock.release()

    def train(self, dataset=None, actor="system"):
        if not self.lock.acquire(blocking=False):
            raise BusyOperation()
        try:
            if self.settings.production:
                raise OperationError(
                    "Train and review model artifacts offline before enabling production ML.", 403
                )
            dataset = dataset or TrainingDataset.model_validate_json(
                (ROOT / "data/ml/synthetic_dataset.json").read_text()
            )
            result = self.model.train(dataset)
            with self.store.connection() as conn:
                audit(
                    conn, actor, "model.trained", result["id"], {"provenance": result["provenance"]}
                )
            return result
        finally:
            self.lock.release()
