"""Shared scan/training operations for requests and scheduled monitoring."""
from pathlib import Path
import threading

from .auth import audit
from .collectors import collect
from .models import Inventory, TrainingDataset
from .monitoring import BusyOperation

ROOT = Path(__file__).resolve().parents[2]


class ScanEngine:
    def __init__(self, store, model, operations):
        self.store, self.model, self.operations = store, model, operations
        self.lock = threading.Lock()

    def _scan(self, inventory, source, actor, origin, collection=None):
        self.model.ensure_default()
        return self.store.scan(inventory, source, model=self.model, collection=collection, phase=3,
            on_snapshot=lambda conn, snapshot: self.operations.snapshot(conn, snapshot, actor, origin))

    def demo(self, actor="system", origin="manual"):
        inventory = Inventory.model_validate_json((ROOT / "data/demo_activity_inventory.json").read_text())
        return self.scan(inventory, "demo", actor, origin)

    def scan(self, inventory, source, actor="system", origin="manual"):
        if not self.lock.acquire(blocking=False):
            raise BusyOperation()
        try:
            return self._scan(inventory, source, actor, origin)
        finally:
            self.lock.release()

    def collect(self, body, actor="system", origin="manual"):
        if not self.lock.acquire(blocking=False):
            raise BusyOperation()
        try:
            inventory, coverage = collect(body)
            return self._scan(inventory, "live", actor, origin, coverage)
        finally:
            self.lock.release()

    def train(self, dataset=None, actor="system"):
        if not self.lock.acquire(blocking=False):
            raise BusyOperation()
        try:
            dataset = dataset or TrainingDataset.model_validate_json((ROOT / "data/ml/synthetic_dataset.json").read_text())
            result = self.model.train(dataset)
            with self.store.connection() as conn:
                audit(conn, actor, "model.trained", result["id"], {"provenance": result["provenance"]})
            return result
        finally:
            self.lock.release()
