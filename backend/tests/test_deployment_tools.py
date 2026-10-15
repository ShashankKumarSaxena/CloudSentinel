"""Verify private archives, offline TLS preparation, and safe retention behavior."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import io
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from backend.app.domain.schemas import Inventory
from backend.app.infrastructure.archives import read_archive, write_archive
from backend.app.repositories.store import Store
from backend.app.services.operations import Operations
from backend.app.services.retention import Retention
from scripts.configure_production import prepare

ROOT = Path(__file__).resolve().parents[2]


class ProductionArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        (self.source / "models").mkdir(parents=True)
        (self.source / "database.dump").write_bytes(b"test-only-database-dump")
        (self.source / "models/active.json").write_text('{"filename":"version.joblib"}')
        (self.source / "models/version.joblib").write_bytes(b"test-only-model-not-loaded")
        self.archive = self.root / "backup.tar.gz"

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_preserves_dump_and_model_bytes_with_private_permissions(self):
        write_archive(self.source, self.archive)
        restored = self.root / "restored"
        restored.mkdir()
        read_archive(self.archive, restored)
        self.assertEqual((restored / "database.dump").read_bytes(), b"test-only-database-dump")
        self.assertEqual(
            (restored / "models/version.joblib").read_bytes(), b"test-only-model-not-loaded"
        )
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)
        self.assertEqual((restored / "database.dump").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            write_archive(self.source, self.archive)

    def test_unsafe_paths_are_rejected_before_any_docker_restore(self):
        with tarfile.open(self.archive, "w:gz") as archive:
            member = tarfile.TarInfo("../escape")
            member.size = 4
            archive.addfile(member, io.BytesIO(b"test"))
        restored = self.root / "restored"
        restored.mkdir()
        with self.assertRaises(ValueError):
            read_archive(self.archive, restored)
        self.assertFalse((self.root / "escape").exists())

    def test_tampered_database_is_rejected(self):
        write_archive(self.source, self.archive)
        altered = self.root / "altered.tar.gz"
        with (
            tarfile.open(self.archive, "r:gz") as original,
            tarfile.open(altered, "w:gz") as target,
        ):
            for member in original:
                with original.extractfile(member) as stream:
                    data = stream.read()
                if member.name == "database.dump":
                    data = b"x" + data[1:]
                target.addfile(member, io.BytesIO(data))
        restored = self.root / "restored"
        restored.mkdir()
        with self.assertRaises(ValueError):
            read_archive(altered, restored)


@unittest.skipUnless(
    shutil.which("openssl"), "OpenSSL is required for offline certificate preparation."
)
class DeploymentPreparationTest(unittest.TestCase):
    def test_generated_database_certificate_verifies_against_private_ca_and_matches_host(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "secrets"
            result = prepare("security.example.com", destination)
            self.assertEqual(result["status"], "prepared")
            self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
            self.assertEqual((destination / "database_ca.key").stat().st_mode & 0o777, 0o600)
            self.assertEqual(len((destination / "database_password").read_text().strip()), 64)
            verified = subprocess.run(
                [
                    "openssl",
                    "verify",
                    "-CAfile",
                    str(destination / "database_ca.crt"),
                    "-verify_hostname",
                    "database",
                    str(destination / "database.crt"),
                ],
                capture_output=True,
                check=True,
            )
            self.assertIn(b"OK", verified.stdout)
            with self.assertRaises(ValueError):
                prepare("security.example.com", destination)

    def test_invalid_hostname_is_rejected_without_creating_secret_files(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "secrets"
            for domain in (
                "https://example.com",
                "example.com/path",
                "a..example.com",
                "bad_name.example.com",
            ):
                with self.assertRaises(ValueError):
                    prepare(domain, destination)
            self.assertFalse(destination.exists())


class RetentionTest(unittest.TestCase):
    def test_dry_run_and_apply_preserve_current_account_snapshots_unfinished_work_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "workspace.db")
            inventory = Inventory.model_validate_json(
                (ROOT / "data/demo_inventory.json").read_text()
            )
            old = store.scan(inventory, "demo")
            current = store.scan(
                inventory, "live", collection={"connection_id": "approved", "region": "ap-south-1"}
            )
            latest = store.scan(inventory, "import")
            old_timestamp = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
            with store.connection() as connection:
                for index, snapshot in enumerate((old, current, latest)):
                    timestamp = (
                        datetime.fromisoformat(old_timestamp) + timedelta(seconds=index)
                    ).isoformat()
                    connection.execute(
                        "UPDATE scans SET created_at=? WHERE id=?", (timestamp, snapshot["id"])
                    )
                connection.execute(
                    "INSERT INTO audit_log (created_at,actor,action,target,detail) VALUES (?,'owner','test','old','{}')",
                    (old_timestamp,),
                )
            with store.connection() as connection:
                for status in ("pending", "running", "succeeded"):
                    connection.execute(
                        "INSERT INTO collection_jobs (id,idempotency_key,created_at,created_by,payload,status) VALUES (?,?,?,?,?,?)",
                        (status, status, old_timestamp, "test", "{}", status),
                    )
            retention = Retention(store)
            self.assertEqual(retention.run(90)["records"]["scans"], 1)
            self.assertIsNotNone(store.get_scan(old["id"]))
            result = retention.run(90, apply=True)
            self.assertTrue(result["applied"])
            self.assertEqual(result["records"]["collection_jobs"], 1)
            with store.connection() as connection:
                self.assertEqual(
                    {row[0] for row in connection.execute("SELECT status FROM collection_jobs")},
                    {"pending", "running"},
                )
            self.assertIsNone(store.get_scan(old["id"]))
            self.assertIsNotNone(store.get_scan(current["id"]))
            self.assertIsNotNone(store.get_scan(latest["id"]))
            self.assertTrue(
                any(row["action"] == "test" for row in Operations(store).audit_records())
            )
            with self.assertRaises(ValueError):
                retention.run(1, apply=True)
