"""Opt-in real PostgreSQL checks; every run uses a disposable private schema.

Set CLOUDSENTINEL_TEST_DATABASE_URL to a dedicated test database. The test role
must be able to create schemas. Never point integration tests at a live workspace.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import json
import os
import tempfile
import unittest

from backend.app.core.config import Settings
from backend.app.domain.schemas import CollectionRequest, Inventory, UserCreate
from backend.app.infrastructure.connections import Connections
from backend.app.repositories.store import Store
from backend.app.services.auth import AuthService
from backend.app.services.jobs import CollectionJobs

DATABASE_URL = os.environ.get("CLOUDSENTINEL_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(DATABASE_URL, "Set a dedicated PostgreSQL test database URL to run.")
class PostgreSQLIntegrationTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.schema = "cloudsentinel_test_" + uuid4().hex
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))

        def remove_schema():
            with psycopg.connect(DATABASE_URL) as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

        self.addCleanup(remove_schema)
        url = make_conninfo(DATABASE_URL, options="-csearch_path=" + self.schema)
        self.path = Path(self.temp.name) / "unused.db"
        self.store = Store(self.path, url)
        self.addCleanup(self.store.database.close)
        self.url = url

    def test_migrations_sessions_and_snapshot_metadata_round_trip(self):
        auth = AuthService(self.store)
        auth.create_user(
            UserCreate(
                username="owner",
                display_name="Owner",
                role="admin",
                password="test-only-long-password",
            ),
            bootstrap=True,
        )
        token, _ = auth.login("owner", "test-only-long-password")
        self.assertEqual(auth.session(token)["user"]["role"], "admin")
        inventory = Inventory.model_validate_json((ROOT / "data/demo_inventory.json").read_text())
        snapshot = self.store.scan(inventory, "import")
        self.assertEqual(self.store.list_scans()[0]["summary"], snapshot["summary"])
        second = Store(self.path, self.url)
        self.addCleanup(second.database.close)
        with second.connection() as conn:
            versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations")]
        self.assertEqual(len(versions), len(set(versions)))
        self.assertEqual(second.get_scan()["id"], snapshot["id"])

    def test_queue_claims_rollback_and_singleton_lock_use_real_postgresql(self):
        registry = Path(self.temp.name) / "accounts.json"
        registry.write_text(
            json.dumps(
                {
                    "accounts": [
                        {
                            "id": "aws-test",
                            "name": "Test account",
                            "provider": "aws",
                            "account": "123456789012",
                            "regions": ["ap-south-1"],
                            "auth": "default",
                            "enabled": True,
                        }
                    ]
                }
            )
        )
        settings = Settings(accounts_file=registry, allow_live_in_demo=True)
        jobs = CollectionJobs(self.store, Connections(registry), settings)
        jobs.begin_worker()
        queued = jobs.submit(
            CollectionRequest(provider="aws", connection_id="aws-test"),
            "owner",
            "test-request-0001",
        )
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda _: jobs.claim(), range(4)))
        self.assertEqual(sum(claim is not None for claim in claims), 1)
        jobs.finish(queued["id"])
        self.assertEqual(jobs.get(queued["id"])["status"], "failed")
        with self.assertRaises(RuntimeError):
            with self.store.connection() as conn:
                conn.execute("DELETE FROM collection_jobs")
                raise RuntimeError("test rollback")
        self.assertEqual(jobs.list()["total"], 1)
        lock = self.store.database.lock_worker()
        try:
            with self.assertRaises(RuntimeError):
                self.store.database.lock_worker()
        finally:
            lock.close()
