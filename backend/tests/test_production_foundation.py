"""Regression coverage for deployment boundaries, account isolation and queued work."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch
import json
import tempfile
import unittest

from pydantic import SecretStr, ValidationError

from backend.app.core.config import Settings
from backend.app.domain.cloud import CloudAccount
from backend.app.domain.schemas import CollectionRequest, Inventory, UserCreate, UserUpdate
from backend.app.infrastructure.collectors.base import CollectionError
from backend.app.infrastructure.connections import Connections
from backend.app.repositories.store import Store
from backend.app.services.auth import AuthError, AuthService
from backend.app.services.engine import ScanEngine
from backend.app.services.jobs import CollectionJobs
from backend.app.services.monitoring import MonitorWorker
from backend.app.services.operations import OperationError, Operations

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "test-only-long-password"


def approved_account(**overrides):
    return (
        dict(
            id="aws-security",
            name="Security account",
            provider="aws",
            account="123456789012",
            regions=["ap-south-1"],
            enabled=True,
            auth="default",
        )
        | overrides
    )


class ConfigurationTest(unittest.TestCase):
    def test_production_fails_closed_with_demo_defaults(self):
        with self.assertRaises(ValidationError):
            Settings(mode="production")

    def test_production_requires_https_database_registry_and_separate_worker(self):
        valid = dict(
            mode="production",
            public_url="https://security.example.com",
            allowed_hosts=("security.example.com",),
            secure_cookies=True,
            embedded_worker=False,
            database_url=SecretStr("postgresql://test:test@database/cloudsentinel"),
            accounts_file=Path("/config/accounts.json"),
            model_dir=Path("/data/models"),
        )
        self.assertTrue(Settings(**valid).production)
        for override in (
            {"secure_cookies": False},
            {"public_url": "http://security.example.com"},
            {"database_url": None},
            {"accounts_file": None},
            {"model_dir": None},
            {"embedded_worker": True},
            {"allowed_hosts": ("*",)},
        ):
            with self.subTest(override=next(iter(override))), self.assertRaises(ValidationError):
                Settings(**(valid | override))

    def test_invalid_boolean_configuration_does_not_silently_disable_security(self):
        with (
            patch.dict("os.environ", {"CLOUDSENTINEL_SECURE_COOKIES": "yes"}),
            self.assertRaises(ValueError),
        ):
            Settings.from_env()

    def test_oidc_configuration_must_be_complete_and_use_https(self):
        with self.assertRaises(ValidationError):
            Settings(oidc_issuer="https://identity.example.com")
        with self.assertRaises(ValidationError):
            Settings(
                oidc_issuer="http://identity.example.com",
                oidc_client_id="test",
                oidc_client_secret_file=Path("/secret"),
                oidc_state_secret_file=Path("/state"),
            )

    def test_cross_account_aws_role_requires_bound_account_and_external_id(self):
        account = CloudAccount.model_validate(
            approved_account(
                auth="assume_role",
                aws_role_arn="arn:aws:iam::123456789012:role/CloudSentinelReadOnly",
                aws_external_id="test-external-id",
            )
        )
        self.assertEqual(account.auth, "assume_role")
        for change in (
            {"aws_external_id": None},
            {"aws_role_arn": "arn:aws:iam::999999999999:role/Other"},
        ):
            with self.assertRaises(ValidationError):
                CloudAccount.model_validate(account.model_dump() | change)
        self.assertNotIn("aws_external_id", account.public())
        self.assertNotIn("aws_role_arn", account.public())


class ProductionFoundationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "workspace.db")
        self.registry_path = self.root / "accounts.json"
        self.write_registry([approved_account()])
        self.connections = Connections(self.registry_path, required=True)
        self.settings = Settings(
            accounts_file=self.registry_path, max_pending_jobs=2, allow_live_in_demo=True
        )
        self.jobs = CollectionJobs(self.store, self.connections, self.settings)
        self.jobs.begin_worker()
        self.operations = Operations(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def write_registry(self, accounts):
        self.registry_path.write_text(json.dumps({"schema_version": "1", "accounts": accounts}))

    def request(self, **changes):
        return CollectionRequest(provider="aws", connection_id="aws-security", **changes)

    def inventory(self, account="123456789012"):
        data = json.loads((ROOT / "data/demo_inventory.json").read_text())
        data["resources"] = [
            resource | {"account": account}
            for resource in data["resources"]
            if resource["provider"] == "aws"
        ]
        return Inventory.model_validate(data)

    def test_registry_rejects_unapproved_disabled_and_cross_account_scope(self):
        for body in (
            self.request(region="us-east-1"),
            self.request(account="999999999999"),
            CollectionRequest(provider="gcp", connection_id="aws-security"),
        ):
            with self.assertRaises(CollectionError):
                self.connections.resolve(body)
        self.write_registry([approved_account(enabled=False)])
        with self.assertRaises(CollectionError):
            self.connections.resolve(self.request())

    def test_duplicate_registry_ids_and_unknown_secret_fields_fail_before_collection(self):
        for entries in (
            [approved_account(), approved_account()],
            [approved_account(access_key="forbidden")],
        ):
            self.write_registry(entries)
            with self.assertRaises(ValueError):
                Connections(self.registry_path)

    def test_submission_is_idempotent_but_reusing_a_key_for_other_work_is_rejected(self):
        first = self.jobs.submit(self.request(), "analyst", "request-key-0001")
        self.assertEqual(
            self.jobs.submit(self.request(), "analyst", "request-key-0001")["id"], first["id"]
        )
        with self.assertRaises(OperationError):
            self.jobs.submit(self.request(lookback_hours=6), "analyst", "request-key-0001")
        self.assertEqual(self.jobs.list()["total"], 1)

    def test_queue_capacity_and_cancellation_are_transactional(self):
        one = self.jobs.submit(self.request(), "analyst", "request-key-0001")
        self.jobs.submit(self.request(), "analyst", "request-key-0002")
        with self.assertRaises(OperationError) as error:
            self.jobs.submit(self.request(), "analyst", "request-key-0003")
        self.assertEqual(error.exception.status, 429)
        self.jobs.cancel(one["id"], "analyst")
        self.assertEqual(self.jobs.get(one["id"])["status"], "cancelled")
        self.jobs.submit(self.request(), "analyst", "request-key-0003")
        claim = self.jobs.claim()
        with self.assertRaises(OperationError):
            self.jobs.cancel(claim["id"], "analyst")

    def test_concurrent_workers_cannot_claim_the_same_job(self):
        self.jobs.submit(self.request(), "analyst", "request-key-0001")
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda _: self.jobs.claim(), range(4)))
        self.assertEqual(sum(claim is not None for claim in claims), 1)

    def test_worker_rechecks_registry_before_touching_cloud_and_records_safe_failure(self):
        self.jobs.submit(self.request(), "analyst", "request-key-0001")
        self.write_registry([approved_account(enabled=False)])
        engine = ScanEngine(self.store, Mock(), self.operations, self.settings, self.connections)
        worker = MonitorWorker(self.operations, engine, Mock(enabled=False), jobs=self.jobs)
        with patch("backend.app.services.engine.collect_approved") as collect:
            worker.tick()
            collect.assert_not_called()
        job = self.jobs.list()["items"][0]
        self.assertEqual(job["status"], "failed")
        self.assertIsNone(self.store.get_scan())

    def test_worker_persists_success_and_separate_account_snapshot_without_synthetic_ml(self):
        queued = self.jobs.submit(self.request(), "analyst", "request-key-0001")
        model = Mock()
        engine = ScanEngine(self.store, model, self.operations, self.settings, self.connections)
        worker = MonitorWorker(self.operations, engine, Mock(enabled=False), jobs=self.jobs)
        with patch(
            "backend.app.services.engine.collect_approved",
            return_value=(
                self.inventory(),
                {"provider": "aws", "account": "123456789012", "partial": False, "coverage": []},
            ),
        ):
            worker.tick()
        job = self.jobs.get(queued["id"])
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(self.store.account_snapshots()[0]["scan_id"], job["scan_id"])
        scan = self.store.get_scan(job["scan_id"])
        self.assertFalse(scan["analysis"]["ml_enabled"])
        self.assertIsNone(scan["activity"]["model"])
        model.ensure_default.assert_not_called()
        model.score.assert_not_called()

    def test_recovery_is_bounded_after_repeated_worker_crashes(self):
        job = self.jobs.submit(self.request(), "analyst", "request-key-0001")
        for _ in range(3):
            self.assertIsNotNone(self.jobs.claim())
            self.jobs.recover()
        self.assertEqual(self.jobs.get(job["id"])["status"], "failed")

    def test_finding_identity_and_triage_are_isolated_by_account(self):
        first = self.store.scan(
            self.inventory(), "live", collection={"connection_id": "first", "region": "ap-south-1"}
        )
        second = self.store.scan(
            self.inventory("999999999999"),
            "live",
            collection={"connection_id": "second", "region": "ap-south-1"},
        )
        first_ids = {finding["id"] for finding in first["findings"]}
        self.assertFalse(first_ids & {finding["id"] for finding in second["findings"]})
        finding_id = first["findings"][0]["id"]
        self.store.triage(finding_id, "resolved", first["id"])
        self.assertEqual(self.store.get_scan(first["id"])["findings"][0]["status"], "resolved")
        self.assertTrue(
            all(
                finding["status"] == "open"
                for finding in self.store.get_scan(second["id"])["findings"]
            )
        )
        replacement = self.store.scan(
            self.inventory(), "live", collection={"connection_id": "first", "region": "ap-south-1"}
        )
        self.assertIsNone(self.store.triage(finding_id, "open", first["id"]))
        self.assertIsNotNone(self.store.triage(finding_id, "open", replacement["id"]))

    def test_failed_scan_transaction_does_not_replace_account_pointer(self):
        metadata = {"connection_id": "first", "region": "ap-south-1"}
        first = self.store.scan(self.inventory(), "live", collection=metadata)
        with self.assertRaises(RuntimeError):
            self.store.scan(
                self.inventory(),
                "live",
                collection=metadata,
                on_snapshot=Mock(side_effect=RuntimeError("test transaction failure")),
            )
        self.assertEqual(self.store.account_snapshots()[0]["scan_id"], first["id"])

    def test_triage_rolls_back_when_the_associated_audit_cannot_be_saved(self):
        snapshot = self.store.scan(self.inventory(), "import")
        finding_id = snapshot["findings"][0]["id"]
        with self.assertRaises(RuntimeError):
            self.store.triage(
                finding_id,
                "resolved",
                snapshot["id"],
                on_change=Mock(side_effect=RuntimeError("test audit failure")),
            )
        self.assertEqual(self.store.get_scan()["findings"][0]["status"], "open")
        self.assertEqual(self.store.events(finding_id), [])

    def test_same_resource_id_in_separate_accounts_is_valid_but_same_account_duplicate_is_not(self):
        data = self.inventory().model_dump()
        data["resources"].append(data["resources"][0] | {"account": "999999999999"})
        Inventory.model_validate(data)
        data["resources"].append(data["resources"][0])
        with self.assertRaises(ValidationError):
            Inventory.model_validate(data)

    def test_schema_migrations_are_idempotent_and_concurrent_startup_is_safe(self):
        path = self.root / "concurrent.db"
        with ThreadPoolExecutor(max_workers=2) as pool:
            stores = list(pool.map(lambda _: Store(path), range(2)))
        with stores[0].connection() as connection:
            applied = connection.execute("SELECT version FROM schema_migrations").fetchall()
            self.assertEqual(len(applied), len({row[0] for row in applied}))
            self.assertTrue(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE name='account_snapshots'"
                ).fetchone()
            )


class CorporateIdentityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.auth = AuthService(Store(Path(self.temp.name) / "identity.db"))
        self.owner = self.auth.create_user(
            UserCreate(username="owner", display_name="Owner", password=PASSWORD, role="admin"),
            bootstrap=True,
        )
        self.user = self.auth.create_user(
            UserCreate(
                username="analyst", display_name="Analyst", password=PASSWORD, role="analyst"
            ),
            "owner",
        )
        self.issuer = "https://identity.example.com"

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_subject_mapping_does_not_autoprovision_or_accept_other_issuer(self):
        self.auth.link_identity(self.user["id"], self.issuer, "approved-subject", "owner")
        token, session = self.auth.login_external(self.issuer, "approved-subject")
        self.assertEqual(session["user"]["role"], "analyst")
        self.assertTrue(session["user"]["sso_only"])
        self.assertIsNotNone(self.auth.session(token))
        for issuer, subject in (
            (self.issuer, "unapproved"),
            ("https://other.example.com", "approved-subject"),
        ):
            with self.assertRaises(AuthError):
                self.auth.login_external(issuer, subject)
        with self.assertRaises(AuthError):
            self.auth.login("analyst", PASSWORD)

    def test_disabled_identity_cannot_sign_in_and_recovery_admin_is_preserved(self):
        with self.assertRaises(AuthError):
            self.auth.link_identity(self.owner["id"], self.issuer, "owner-subject", "owner")
        self.auth.link_identity(self.user["id"], self.issuer, "approved-subject", "owner")
        self.auth.update_user(self.user["id"], UserUpdate(enabled=False), "owner")
        with self.assertRaises(AuthError):
            self.auth.login_external(self.issuer, "approved-subject")


class WorkerAndAlertLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "lifecycle.db")
        self.operations = Operations(self.store)
        self.inventory = Inventory.model_validate_json(
            (ROOT / "data/demo_inventory.json").read_text()
        )

    def tearDown(self):
        self.temp.cleanup()

    def record(self, inventory):
        return self.store.scan(
            inventory,
            "import",
            on_snapshot=lambda conn, snapshot: self.operations.snapshot(conn, snapshot, "analyst"),
        )

    def test_configuration_alert_reopens_after_explicit_pass_then_new_failure(self):
        first = self.record(self.inventory)
        target = next(finding for finding in first["findings"] if finding["rule_id"] == "STO-001")
        before = self.operations.list_alerts()["total"]
        data = self.inventory.model_dump()
        for resource in data["resources"]:
            if (
                resource["provider"] == target["provider"]
                and resource["id"] == target["resource_id"]
            ):
                resource["config"]["public_access"] = False
        self.record(Inventory.model_validate(data))
        self.record(self.inventory)
        self.assertEqual(self.operations.list_alerts()["total"], before + 1)
        self.record(self.inventory)
        self.assertEqual(self.operations.list_alerts()["total"], before + 1)

    def test_resolved_configuration_reopens_when_next_scan_still_fails(self):
        first = self.record(self.inventory)
        finding_id = first["findings"][0]["id"]
        self.store.triage(finding_id, "resolved")
        before = self.operations.list_alerts()["total"]
        next_scan = self.record(self.inventory)
        self.assertEqual(
            next(finding for finding in next_scan["findings"] if finding["id"] == finding_id)[
                "status"
            ],
            "open",
        )
        self.assertEqual(self.operations.list_alerts()["total"], before + 1)
        self.assertTrue(
            any(row["action"] == "finding.reopened" for row in self.operations.audit_records())
        )

    def test_obsolete_worker_cannot_finish_job_or_publish_snapshot(self):
        from backend.app.services.jobs import WorkerOwnershipLost

        registry = Path(self.temp.name) / "accounts.json"
        registry.write_text(json.dumps({"schema_version": "1", "accounts": [approved_account()]}))
        connections = Connections(registry)
        settings = Settings(allow_live_in_demo=True)
        old = CollectionJobs(self.store, connections, settings)
        old.begin_worker()
        submitted = old.submit(
            CollectionRequest(provider="aws", connection_id="aws-security"),
            "analyst",
            "test-key-0001",
        )
        old.claim()
        engine = ScanEngine(self.store, Mock(), self.operations, settings, connections)
        engine.worker_owner = old.owner
        replacement = CollectionJobs(self.store, connections, settings)
        replacement.begin_worker()
        with self.assertRaises(WorkerOwnershipLost):
            old.heartbeat()
        with self.assertRaises(WorkerOwnershipLost):
            old.finish(submitted["id"], scan_id="obsolete")
        data = self.inventory.model_dump()
        data["resources"] = [
            resource | {"account": "123456789012"}
            for resource in data["resources"]
            if resource["provider"] == "aws"
        ]
        with (
            patch(
                "backend.app.services.engine.collect_approved",
                return_value=(Inventory.model_validate(data), {}),
            ),
            self.assertRaises(WorkerOwnershipLost),
        ):
            engine.collect(CollectionRequest(provider="aws", connection_id="aws-security"))
        self.assertIsNone(self.store.get_scan())
        self.assertEqual(self.store.account_snapshots(), [])

    def test_demo_mode_rejects_live_collection_before_sdk_initialization(self):
        engine = ScanEngine(self.store, Mock(), self.operations)
        with (
            patch("backend.app.services.engine.collect") as collect,
            self.assertRaises(OperationError),
        ):
            engine.collect(CollectionRequest(provider="aws"))
        collect.assert_not_called()
