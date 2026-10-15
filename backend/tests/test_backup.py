from pathlib import Path
import io
import json
import tarfile
import tempfile
import unittest

from backend.app.domain.schemas import Inventory, ScheduleCreate, UserCreate
from backend.app.repositories.store import Store
from backend.app.services.auth import AuthService
from backend.app.services.operations import Operations
from scripts.backup import backup, restore


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "source/cloudsentinel.db")
        self.auth = AuthService(self.store)
        self.auth.create_user(
            UserCreate(
                username="owner",
                display_name="Owner",
                password="test-only-long-password",
                role="admin",
            ),
            bootstrap=True,
        )
        self.auth.login("owner", "test-only-long-password")
        self.operations = Operations(self.store, email_enabled=True)
        self.operations.create_schedule(ScheduleCreate(name="Restorable monitor"), "owner")
        with self.store.connection() as conn:
            self.operations.insert_alert(
                conn, "pending-email", "finding", "critical", "Test finding", "demo", {}
            )

    def tearDown(self):
        self.temp.cleanup()

    def test_backup_round_trip_preserves_data_but_revokes_sessions_and_pauses_automation(self):
        fixture = Path(__file__).resolve().parents[2] / "data/demo_inventory.json"
        scan = self.store.scan(Inventory.model_validate_json(fixture.read_text()), "demo")
        models = self.store.path.parent / "models"
        models.mkdir()
        (models / "test.joblib").write_bytes(b"test-only-artifact-not-loaded")
        (models / "active.json").write_text(json.dumps({"artifact": "test.joblib"}))
        with self.store.connection() as conn:
            conn.execute(
                "INSERT INTO worker_heartbeat VALUES (1,'2026-01-01T00:00:00+00:00','running','test-worker')"
            )
            conn.execute(
                "INSERT INTO collection_jobs (id,idempotency_key,created_at,created_by,payload,status) VALUES ('pending','test','2026-01-01T00:00:00+00:00','owner','{}','pending')"
            )
        archive = self.root / "backup.tar.gz"
        backup(self.store.path, archive)
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        restored_db = self.root / "restored/cloudsentinel.db"
        restore(archive, restored_db)
        restored = Store(restored_db)
        self.assertEqual(AuthService(restored).list_users()[0]["username"], "owner")
        self.assertEqual(restored.get_scan()["id"], scan["id"])
        self.assertEqual(
            (restored_db.parent / "models/test.joblib").read_bytes(),
            b"test-only-artifact-not-loaded",
        )
        self.assertEqual(
            json.loads((restored_db.parent / "models/active.json").read_text()),
            {"artifact": "test.joblib"},
        )
        with restored.connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT enabled FROM schedules").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM worker_heartbeat").fetchone()[0], 0)
            self.assertEqual(
                conn.execute("SELECT status FROM collection_jobs").fetchone()[0], "cancelled"
            )
            self.assertEqual(
                conn.execute("SELECT delivery FROM alerts").fetchone()[0], "inbox_only"
            )
        with self.store.connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)

    def test_restore_cannot_overwrite_existing_data(self):
        archive = self.root / "backup.tar.gz"
        backup(self.store.path, archive)
        with self.assertRaises(ValueError):
            restore(archive, self.store.path)

    def test_restore_rejects_existing_model_directory_even_without_model_archive(self):
        archive = self.root / "backup.tar.gz"
        backup(self.store.path, archive)
        destination = self.root / "restored/cloudsentinel.db"
        (destination.parent / "models").mkdir(parents=True)
        with self.assertRaises(ValueError):
            restore(archive, destination)
        self.assertFalse(destination.exists())

    def test_restore_rejects_unsafe_archive_paths(self):
        archive = self.root / "unsafe.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            item = tarfile.TarInfo("../outside")
            item.size = 4
            handle.addfile(item, io.BytesIO(b"test"))
        target = self.root / "restored/cloudsentinel.db"
        with self.assertRaises(ValueError):
            restore(archive, target)
        self.assertFalse(target.exists())

    def test_restore_rejects_checksum_changes_before_publishing_database(self):
        archive = self.root / "backup.tar.gz"
        backup(self.store.path, archive)
        altered = self.root / "altered.tar.gz"
        with tarfile.open(archive, "r:gz") as source, tarfile.open(altered, "w:gz") as destination:
            for item in source.getmembers():
                content = source.extractfile(item).read()
                if item.name == "cloudsentinel.db":
                    content = content[:-1] + bytes([content[-1] ^ 1])
                destination.addfile(item, io.BytesIO(content))
        target = self.root / "restored/cloudsentinel.db"
        with self.assertRaises(ValueError):
            restore(altered, target)
        self.assertFalse(target.exists())
