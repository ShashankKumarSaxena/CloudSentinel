"""Production HTTP policies exercised with a real temporary SQLite test adapter.

PostgreSQL transport and SDK integration have separate opt-in tests. The test
adapter is patched only in this suite; production configuration still requires PG.
"""

import asyncio
from pathlib import Path
from unittest.mock import patch
import json
import tempfile
import unittest

from pydantic import SecretStr

from backend.app.application import create_app
from backend.app.core.config import Settings
from backend.app.domain.schemas import UserCreate
from backend.app.repositories.store import Store
from backend.tests.asgi_client import call

PASSWORD = "test-only-long-password"


class ProductionApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.registry = root / "accounts.json"
        self.registry.write_text(
            json.dumps(
                {
                    "schema_version": "1",
                    "accounts": [
                        {
                            "id": "security-account",
                            "name": "Security",
                            "provider": "aws",
                            "account": "123456789012",
                            "regions": ["ap-south-1"],
                            "auth": "default",
                            "enabled": True,
                        }
                    ],
                }
            )
        )
        settings = Settings(
            mode="production",
            public_url="https://testserver",
            allowed_hosts=("testserver",),
            secure_cookies=True,
            embedded_worker=False,
            accounts_file=self.registry,
            model_dir=root / "models",
            database_path=root / "workspace.db",
            database_url=SecretStr("postgresql://test:test@database/cloudsentinel_test"),
        )
        with (
            patch("backend.app.application.Store", side_effect=lambda path, url: Store(path)),
            patch("backend.app.api.observability.logger"),
        ):
            self.app = await asyncio.to_thread(create_app, settings=settings)
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        await asyncio.to_thread(
            self.app.state.auth.create_user,
            UserCreate(username="owner", display_name="Owner", password=PASSWORD, role="admin"),
            bootstrap=True,
        )
        status, session, headers = await call(
            self.app, "POST", "/api/v1/auth/login", {"username": "owner", "password": PASSWORD}
        )
        self.assertEqual(status, 200)
        self.assertIn("Secure", headers["set-cookie"])
        self.app._test_headers = {
            "cookie": headers["set-cookie"].split(";")[0],
            "x-csrf-token": session["csrf_token"],
        }

    async def asyncTearDown(self):
        await self.lifespan.__aexit__(None, None, None)
        self.temp.cleanup()

    async def test_startup_has_no_synthetic_scan_or_model_and_empty_workspace_is_usable(self):
        self.assertIsNone(self.app.state.store.get_scan())
        self.assertFalse(self.app.state.model.status()["ready"])
        status, data, _ = await call(self.app, "GET", "/api/v1/workspace")
        self.assertEqual(status, 200)
        self.assertFalse(data["demo_enabled"])
        for path in ("/cloud/accounts", "/cloud/jobs", "/users", "/operations"):
            status, _, _ = await call(self.app, "GET", "/api/v1" + path)
            self.assertEqual(status, 200)

    async def test_synthetic_scan_training_and_unapproved_sync_collection_are_blocked(self):
        for path in ("/scans/demo", "/model/train/demo"):
            status, _, _ = await call(self.app, "POST", "/api/v1" + path)
            self.assertEqual(status, 403)
        status, _, _ = await call(self.app, "POST", "/api/v1/scans/collect", {"provider": "aws"})
        self.assertEqual(status, 409)
        status, _, _ = await call(self.app, "POST", "/api/v1/schedules", {"name": "Forbidden demo"})
        self.assertEqual(status, 403)

    async def test_job_submission_returns_202_without_contacting_cloud_and_requires_key(self):
        body = {"provider": "aws", "connection_id": "security-account"}
        with patch("backend.app.services.engine.collect_approved") as collect:
            status, _, _ = await call(self.app, "POST", "/api/v1/cloud/jobs", body)
            self.assertEqual(status, 400)
            status, job, _ = await call(
                self.app,
                "POST",
                "/api/v1/cloud/jobs",
                body,
                headers={"idempotency-key": "request-key-0001"},
            )
            self.assertEqual(status, 202)
            self.assertEqual(job["status"], "pending")
            collect.assert_not_called()
        status, second, _ = await call(
            self.app,
            "POST",
            "/api/v1/cloud/jobs",
            body,
            headers={"idempotency-key": "request-key-0001"},
        )
        self.assertEqual(status, 202)
        self.assertEqual(job["id"], second["id"])

    async def test_production_origin_is_exact_and_readiness_requires_dedicated_worker(self):
        status, _, _ = await call(
            self.app,
            "POST",
            "/api/v1/cloud/jobs",
            {"provider": "aws", "connection_id": "security-account"},
            headers={"origin": "http://localhost:5173", "idempotency-key": "request-key-0001"},
        )
        self.assertEqual(status, 403)
        status, ready, _ = await call(self.app, "GET", "/api/v1/ready")
        self.assertEqual(status, 503)
        self.app.state.jobs.begin_worker()
        self.app.state.jobs.heartbeat()
        status, ready, _ = await call(self.app, "GET", "/api/v1/ready")
        self.assertEqual(status, 200)
        self.assertTrue(ready["ready"])
        self.assertFalse(ready["model_ready"])

    async def test_unknown_and_disabled_account_job_is_rejected_without_leaking_credentials(self):
        status, data, _ = await call(
            self.app,
            "POST",
            "/api/v1/cloud/jobs",
            {"provider": "aws", "connection_id": "unapproved"},
            headers={"idempotency-key": "request-key-0001"},
        )
        self.assertEqual(status, 502)
        self.assertIn("approved", data["detail"])
        self.assertNotIn("postgresql", json.dumps(data))
