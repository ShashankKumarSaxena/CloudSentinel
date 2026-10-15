from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import unittest

from backend.app.domain.schemas import ScheduleCreate, ScheduleUpdate
from backend.app.repositories.store import Store
from backend.app.services.engine import ScanEngine
from backend.app.services.model import ModelService
from backend.app.services.monitoring import MonitorWorker
from backend.app.services.operations import OperationError, Operations

ROOT = Path(__file__).resolve().parents[2]


class OperationsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "operations.db")
        self.operations = Operations(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def schedule(self, **changes):
        return self.operations.create_schedule(
            ScheduleCreate(name="Test monitor", interval_seconds=60, **changes), "owner"
        )

    def due(self, schedule):
        with self.store.connection() as conn:
            conn.execute(
                "UPDATE schedules SET next_run=? WHERE id=?",
                ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), schedule["id"]),
            )

    def test_schedule_persists_and_only_one_concurrent_claim_succeeds(self):
        schedule = self.schedule()
        self.due(schedule)
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda _: self.operations.claim_schedule(), range(4)))
        self.assertEqual(sum(c is not None for c in claims), 1)
        reopened = Operations(Store(self.store.path))
        self.assertEqual(reopened.list_schedules()[0]["last_status"], "running")
        self.assertEqual(len(reopened.list_runs()), 1)

    def test_paused_schedules_do_not_run_but_manual_run_is_explicit(self):
        schedule = self.schedule(enabled=False)
        self.due(schedule)
        self.assertIsNone(self.operations.claim_schedule())
        claim = self.operations.claim_schedule(schedule["id"])
        self.assertIsNotNone(claim)
        with self.assertRaises(OperationError):
            self.operations.update_schedule(schedule["id"], ScheduleUpdate(enabled=True), "owner")

    def test_failure_backoff_and_alerts_are_deduplicated_by_episode(self):
        schedule = self.schedule()
        first = self.operations.claim_schedule(schedule["id"])
        self.operations.finish_schedule(first, error="Safe collection failure")
        row = self.operations.list_schedules()[0]
        self.assertEqual(row["failures"], 1)
        self.assertGreater(
            datetime.fromisoformat(row["next_run"]),
            datetime.now(timezone.utc) + timedelta(seconds=50),
        )
        second = self.operations.claim_schedule(schedule["id"])
        self.operations.finish_schedule(second, error="Safe collection failure")
        self.assertEqual(self.operations.list_schedules()[0]["failures"], 2)
        self.assertEqual(self.operations.list_alerts()["total"], 1)
        success = self.operations.claim_schedule(schedule["id"])
        self.operations.finish_schedule(success, scan_id="test-scan")
        failure = self.operations.claim_schedule(schedule["id"])
        self.operations.finish_schedule(failure, error="New failure episode")
        self.assertEqual(self.operations.list_alerts()["total"], 2)

    def test_busy_run_defers_without_failure_or_alert(self):
        schedule = self.schedule()
        claim = self.operations.claim_schedule(schedule["id"])
        self.operations.finish_schedule(claim, error="Busy", busy=True)
        row = self.operations.list_schedules()[0]
        self.assertEqual(row["last_status"], "deferred")
        self.assertEqual(row["failures"], 0)
        self.assertEqual(self.operations.list_alerts()["total"], 0)

    def test_interrupted_runs_recover_without_inventing_success(self):
        schedule = self.schedule()
        self.operations.claim_schedule(schedule["id"])
        self.operations.recover_interrupted()
        self.assertEqual(self.operations.list_schedules()[0]["last_status"], "interrupted")
        self.assertEqual(self.operations.list_runs()[0]["status"], "interrupted")

    def test_alert_acknowledgement_is_persistent_and_pages_are_bounded(self):
        with self.store.connection() as conn:
            for i in range(3):
                self.operations.insert_alert(
                    conn, f"alert-{i}", "finding", "high", "Test finding", "demo", {}
                )
        page = self.operations.list_alerts(limit=2)
        self.assertEqual(len(page["items"]), 2)
        self.assertEqual(page["unread"], 3)
        self.operations.acknowledge(page["items"][0]["id"], "analyst")
        self.assertEqual(Operations(Store(self.store.path)).list_alerts()["unread"], 2)
        self.assertEqual(len(self.operations.list_alerts(limit=2, offset=2)["items"]), 1)

    def test_email_outbox_retries_then_records_terminal_failure(self):
        operations = Operations(self.store, email_enabled=True)
        with self.store.connection() as conn:
            operations.insert_alert(
                conn, "email-alert", "finding", "critical", "Test finding", "demo", {}
            )
        future = datetime.now(timezone.utc) + timedelta(days=1)
        for expected in range(1, 6):
            alert = operations.claim_delivery(future)
            self.assertEqual(alert["attempts"], expected)
            operations.finish_delivery(alert, False)
        self.assertEqual(operations.list_alerts()["items"][0]["delivery"], "failed")
        self.assertIsNone(operations.claim_delivery(future))
        operations.retry_delivery(alert["id"], "owner")
        self.assertEqual(operations.claim_delivery(future)["attempts"], 1)

    def test_delivery_success_is_not_repeated_and_disabled_email_stays_inbox_only(self):
        with self.store.connection() as conn:
            self.operations.insert_alert(
                conn, "inbox", "finding", "critical", "Test finding", "demo", {}
            )
        self.assertEqual(self.operations.list_alerts()["items"][0]["delivery"], "inbox_only")
        self.assertIsNone(self.operations.claim_delivery())
        operations = Operations(self.store, email_enabled=True)
        with self.store.connection() as conn:
            operations.insert_alert(
                conn, "email", "finding", "critical", "Test finding", "demo", {}
            )
        alert = operations.claim_delivery()
        operations.finish_delivery(alert, True)
        self.assertIsNone(operations.claim_delivery())


class EngineMonitoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model_temp = tempfile.TemporaryDirectory()
        cls.model = ModelService(Path(cls.model_temp.name))
        cls.model.ensure_default()

    @classmethod
    def tearDownClass(cls):
        cls.model_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "engine.db")
        self.operations = Operations(self.store)
        self.engine = ScanEngine(self.store, self.model, self.operations)
        self.delivery = Mock(enabled=False)
        self.worker = MonitorWorker(self.operations, self.engine, self.delivery)

    def tearDown(self):
        self.worker.stop()
        self.temp.cleanup()

    def test_scan_alerts_are_atomic_and_repeated_demo_does_not_flood_inbox(self):
        first = self.engine.demo("owner")
        self.assertEqual(first["phase"], 3)
        self.assertEqual(self.operations.list_alerts()["total"], 19)
        self.engine.demo("owner")
        self.assertEqual(self.operations.list_alerts()["total"], 19)
        self.assertEqual(len(self.store.list_scans()), 2)
        before = self.store.get_scan()["id"]
        with patch.object(
            self.operations, "snapshot", side_effect=RuntimeError("failed alert transaction")
        ):
            with self.assertRaises(RuntimeError):
                self.engine.demo("owner")
        self.assertEqual(self.store.get_scan()["id"], before)
        self.assertEqual(self.operations.list_alerts()["total"], 19)

    def test_due_tick_creates_saved_scan_and_run(self):
        schedule = self.operations.create_schedule(
            ScheduleCreate(name="Synthetic monitor", interval_seconds=60), "owner"
        )
        with self.store.connection() as conn:
            conn.execute(
                "UPDATE schedules SET next_run=?",
                ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),),
            )
        self.worker.tick()
        self.assertEqual(self.operations.list_runs()[0]["status"], "succeeded")
        self.assertEqual(self.operations.list_runs()[0]["scan_id"], self.store.get_scan()["id"])
        self.assertIsNotNone(self.worker.last_tick)

    def test_second_monitor_process_is_rejected_and_shutdown_releases_lock(self):
        self.worker.start()
        other = MonitorWorker(self.operations, self.engine, self.delivery)
        with self.assertRaises(RuntimeError):
            other.start()
        self.worker.stop()
        replacement = MonitorWorker(self.operations, self.engine, self.delivery)
        replacement.start()
        self.assertTrue(replacement.status()["running"])
        replacement.stop()

    def test_collection_failure_is_saved_and_secrets_are_masked(self):
        from backend.app.domain.schemas import CollectionRequest

        schedule = self.operations.create_schedule(
            ScheduleCreate(
                name="Live monitor", kind="live", collection=CollectionRequest(provider="aws")
            ),
            "owner",
        )
        claim = self.operations.claim_schedule(schedule["id"])
        with patch("backend.app.services.engine.collect", side_effect=RuntimeError("SECRET_TOKEN")):
            with self.assertRaises(OperationError):
                self.worker.execute(claim)
        self.assertIsNone(self.store.get_scan())
        self.assertNotIn("SECRET_TOKEN", self.operations.list_runs()[0]["error"])
        self.assertEqual(self.operations.list_alerts()["items"][0]["kind"], "monitor_failure")
