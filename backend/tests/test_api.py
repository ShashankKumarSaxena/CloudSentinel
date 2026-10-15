import asyncio
from pathlib import Path
from unittest.mock import patch
import json
import tempfile
import threading
import unittest

from backend.app.application import MAX_IMPORT_BYTES, create_app
from backend.app.core.config import Settings
from backend.app.domain.schemas import Inventory, UserCreate
from backend.tests.asgi_client import call

ROOT = Path(__file__).resolve().parents[2]


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = await asyncio.to_thread(
            create_app,
            settings=Settings(
                database_path=Path(self.temp.name) / "api.db",
                embedded_worker=False,
                allow_live_in_demo=True,
            ),
        )
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        await asyncio.to_thread(
            self.app.state.auth.create_user,
            UserCreate(
                username="testadmin",
                display_name="Test admin",
                password="test-only-long-password",
                role="admin",
            ),
            bootstrap=True,
        )
        _, session, headers = await call(
            self.app,
            "POST",
            "/api/v1/auth/login",
            {"username": "testadmin", "password": "test-only-long-password"},
        )
        self.app._test_headers = {
            "cookie": headers["set-cookie"].split(";")[0],
            "x-csrf-token": session["csrf_token"],
        }

    async def asyncTearDown(self):
        await self.lifespan.__aexit__(None, None, None)
        self.temp.cleanup()

    async def test_first_start_seeds_one_demo_and_health_is_available(self):
        status, body, headers = await call(self.app, "GET", "/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["phase"], 3)
        self.assertTrue(body["model_ready"])
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual(headers["cache-control"], "no-store")
        _, scans, _ = await call(self.app, "GET", "/api/v1/scans")
        self.assertEqual(len(scans), 1)

    async def test_signed_in_api_reference_is_local_and_schema_is_available(self):
        status, html, headers = await call(self.app, "GET", "/docs")
        self.assertEqual(status, 200)
        self.assertIn(b"CloudSentinel API reference", html)
        self.assertIn(b"/api/v1/schedules", html)
        self.assertNotIn(b"<script", html)
        self.assertNotIn(b"cdn.", html)
        self.assertIn("script-src 'self'", headers["content-security-policy"])
        status, schema, _ = await call(self.app, "GET", "/openapi.json")
        self.assertEqual(status, 200)
        self.assertEqual(schema["info"]["version"], "1.0.0")
        self.assertEqual(schema["paths"]["/api/v1/auth/login"]["post"]["security"], [])
        import_contract = schema["paths"]["/api/v1/scans/import"]["post"]
        self.assertEqual(import_contract["security"], [{"WorkspaceSession": [], "CsrfToken": []}])
        self.assertEqual(import_contract["x-required-roles"], ["analyst", "admin"])
        self.assertIn("requestBody", import_contract)
        self.assertEqual(schema["paths"]["/api/v1/users"]["get"]["x-required-roles"], ["admin"])

    async def test_scan_triage_events_and_export_flow(self):
        status, scan, _ = await call(self.app, "POST", "/api/v1/scans/demo")
        self.assertEqual(status, 201)
        finding_id = scan["findings"][0]["id"]
        status, updated, _ = await call(
            self.app, "PATCH", f"/api/v1/findings/{finding_id}", {"status": "acknowledged"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["status"], "acknowledged")
        _, events, _ = await call(self.app, "GET", f"/api/v1/findings/{finding_id}/events")
        self.assertEqual(events[0]["previous_status"], "open")
        status, report, headers = await call(self.app, "GET", "/api/v1/export")
        self.assertEqual(status, 200)
        self.assertEqual(report["scan"]["summary"]["failed"], 16)
        self.assertEqual(report["scan"]["summary"]["anomalies"], 3)
        self.assertEqual(report["scan"]["summary"]["findings"], 19)
        self.assertIn("deterministic", report["detection_method"])
        self.assertIn("attachment", headers["content-disposition"])

    async def test_import_validates_atomically_and_preserves_unknown_fields(self):
        inventory = json.loads((ROOT / "data/demo_inventory.json").read_text())
        inventory["resources"] = [inventory["resources"][0]]
        inventory["resources"][0]["config"] = {}
        status, scan, _ = await call(self.app, "POST", "/api/v1/scans/import", inventory)
        self.assertEqual(status, 201)
        self.assertEqual(scan["source"], "import")
        self.assertEqual(scan["summary"]["unknown"], 2)
        self.assertIsNone(scan["summary"]["posture_score"])
        inventory["resources"][0]["config"] = {"public_access": "false"}
        status, error, _ = await call(self.app, "POST", "/api/v1/scans/import", inventory)
        self.assertEqual(status, 422)
        self.assertIn("errors", error)
        _, latest, _ = await call(self.app, "GET", "/api/v1/scans/latest")
        self.assertEqual(latest["id"], scan["id"])

    async def test_malformed_json_wrong_type_and_oversize_rejected(self):
        status, _, _ = await call(self.app, "POST", "/api/v1/scans/import", raw=b"{not-json}")
        self.assertEqual(status, 422)
        status, _, _ = await call(
            self.app,
            "POST",
            "/api/v1/scans/import",
            raw=b"{}",
            headers={"content-type": "text/plain"},
        )
        self.assertEqual(status, 415)
        status, _, _ = await call(
            self.app, "POST", "/api/v1/scans/import", raw=b"x" * (MAX_IMPORT_BYTES + 1)
        )
        self.assertEqual(status, 413)

    async def test_cross_origin_writes_and_untrusted_hosts_rejected(self):
        status, _, _ = await call(
            self.app, "POST", "/api/v1/scans/demo", headers={"origin": "https://untrusted.example"}
        )
        self.assertEqual(status, 403)
        status, _, _ = await call(
            self.app, "GET", "/api/v1/health", headers={"host": "untrusted.example"}
        )
        self.assertEqual(status, 400)
        status, _, _ = await call(
            self.app, "POST", "/api/v1/scans/demo", headers={"origin": "http://127.0.0.1:5173"}
        )
        self.assertEqual(status, 201)

    async def test_unknown_scan_finding_and_invalid_status(self):
        for method, path, body, expected in [
            ("GET", "/api/v1/scans/missing", None, 404),
            ("PATCH", "/api/v1/findings/missing", {"status": "open"}, 404),
            ("PATCH", "/api/v1/findings/missing", {"status": "invalid"}, 422),
        ]:
            with self.subTest(path=path, body=body):
                status, _, _ = await call(self.app, method, path, body)
                self.assertEqual(status, expected)

    async def test_restart_does_not_seed_another_demo(self):
        second_app = await asyncio.to_thread(
            create_app, Path(self.temp.name) / "api.db", monitoring_enabled=False
        )
        second_app._test_headers = self.app._test_headers
        async with second_app.router.lifespan_context(second_app):
            _, scans, _ = await call(second_app, "GET", "/api/v1/scans")
            self.assertEqual(len(scans), 1)

    async def test_model_metadata_training_and_activity_import(self):
        status, model, _ = await call(self.app, "GET", "/api/v1/model")
        self.assertEqual(status, 200)
        self.assertEqual(model["algorithm"], "Isolation Forest")
        self.assertEqual(model["provenance"], "synthetic")
        status, retrained, _ = await call(self.app, "POST", "/api/v1/model/train/demo")
        self.assertEqual(status, 200)
        self.assertNotEqual(retrained["id"], model["id"])
        dataset = json.loads((ROOT / "data/ml/synthetic_dataset.json").read_text())
        status, retrained, _ = await call(self.app, "POST", "/api/v1/model/train", dataset)
        self.assertEqual(status, 200)
        self.assertNotEqual(retrained["id"], model["id"])
        inventory = json.loads((ROOT / "data/demo_activity_inventory.json").read_text())
        status, scan, _ = await call(self.app, "POST", "/api/v1/scans/import", inventory)
        self.assertEqual(status, 201)
        self.assertEqual(scan["activity"]["event_count"], 330)
        self.assertEqual(len(scan["activity"]["windows"]), 6)
        self.assertEqual(scan["activity"]["model"]["id"], retrained["id"])
        self.assertEqual(scan["summary"]["anomalies"], 3)

    async def test_invalid_training_preserves_active_model(self):
        _, before, _ = await call(self.app, "GET", "/api/v1/model")
        status, _, _ = await call(self.app, "POST", "/api/v1/model/train", {"name": "invalid"})
        self.assertEqual(status, 422)
        _, after, _ = await call(self.app, "GET", "/api/v1/model")
        self.assertEqual(after["id"], before["id"])

    async def test_live_collection_is_explicit_and_records_coverage(self):
        inventory = Inventory.model_validate_json(
            (ROOT / "data/demo_activity_inventory.json").read_text()
        )
        metadata = {
            "provider": "aws",
            "read_only": True,
            "partial": True,
            "coverage": [{"scope": "IAM", "status": "unavailable"}],
        }
        with patch(
            "backend.app.services.engine.collect", return_value=(inventory, metadata)
        ) as collector:
            status, scan, _ = await call(
                self.app, "POST", "/api/v1/scans/collect", {"provider": "aws"}
            )
            self.assertEqual(status, 201)
            self.assertEqual(scan["source"], "live")
            self.assertTrue(scan["collection"]["partial"])
            collector.assert_called_once()

    async def test_failed_collection_preserves_latest_and_masks_exception(self):
        _, before, _ = await call(self.app, "GET", "/api/v1/scans/latest")
        with patch("backend.app.services.engine.collect", side_effect=RuntimeError("SECRET_TOKEN")):
            status, error, _ = await call(
                self.app, "POST", "/api/v1/scans/collect", {"provider": "aws"}
            )
        self.assertEqual(status, 502)
        self.assertNotIn("SECRET_TOKEN", json.dumps(error))
        _, after, _ = await call(self.app, "GET", "/api/v1/scans/latest")
        self.assertEqual(after["id"], before["id"])

    async def test_connection_status_does_not_make_cloud_calls_or_return_tokens(self):
        with patch("backend.app.services.engine.collect") as collector:
            status, connections, _ = await call(self.app, "GET", "/api/v1/connectors")
            self.assertEqual(status, 200)
            self.assertEqual({c["provider"] for c in connections}, {"aws", "azure", "gcp"})
            collector.assert_not_called()
            self.assertTrue(all("credential_source" in c and "token" not in c for c in connections))

    async def test_concurrent_scan_and_training_rejected_during_collection(self):
        entered, resume = threading.Event(), threading.Event()
        inventory = Inventory.model_validate_json((ROOT / "data/demo_inventory.json").read_text())

        def pending_collection(body):
            entered.set()
            resume.wait(timeout=3)
            return inventory, {"partial": False, "read_only": True, "coverage": []}

        with patch("backend.app.services.engine.collect", side_effect=pending_collection):
            task = asyncio.create_task(
                call(self.app, "POST", "/api/v1/scans/collect", {"provider": "aws"})
            )
            try:
                for _ in range(100):
                    if entered.is_set():
                        break
                    await asyncio.sleep(0.01)
                self.assertTrue(entered.is_set())
                for path in ("/api/v1/scans/demo", "/api/v1/model/train/demo"):
                    status, _, _ = await call(self.app, "POST", path)
                    self.assertEqual(status, 409)
            finally:
                resume.set()
                await task

    @unittest.skipUnless(
        (ROOT / "frontend/dist/index.html").exists(),
        "Build the frontend before checking static serving",
    )
    async def test_built_dashboard_and_assets_are_served_beside_api(self):
        import re

        status, html, headers = await call(self.app, "GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"CloudSentinel", html)
        self.assertEqual(headers["x-frame-options"], "DENY")
        scripts = re.findall(rb'src="(/assets/[^\"]+\.js)"', html)
        self.assertTrue(scripts)
        for asset in scripts:
            status, content, _ = await call(self.app, "GET", asset.decode())
            self.assertEqual(status, 200)
            self.assertTrue(content)


if __name__ == "__main__":
    unittest.main()
