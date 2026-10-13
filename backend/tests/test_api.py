import json
from pathlib import Path
import tempfile
import unittest

from backend.app.main import create_app, MAX_IMPORT_BYTES
from backend.tests.asgi_client import call

ROOT = Path(__file__).resolve().parents[2]


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.temp.name) / "api.db")
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()

    async def asyncTearDown(self):
        await self.lifespan.__aexit__(None, None, None)
        self.temp.cleanup()

    async def test_first_start_seeds_one_demo_and_health_is_available(self):
        status, body, headers = await call(self.app, "GET", "/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["phase"], 1)
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual(headers["cache-control"], "no-store")
        _, scans, _ = await call(self.app, "GET", "/api/v1/scans")
        self.assertEqual(len(scans), 1)

    async def test_scan_triage_events_and_export_flow(self):
        status, scan, _ = await call(self.app, "POST", "/api/v1/scans/demo")
        self.assertEqual(status, 201)
        finding_id = scan["findings"][0]["id"]
        status, updated, _ = await call(self.app, "PATCH", f"/api/v1/findings/{finding_id}", {"status": "acknowledged"})
        self.assertEqual(status, 200)
        self.assertEqual(updated["status"], "acknowledged")
        _, events, _ = await call(self.app, "GET", f"/api/v1/findings/{finding_id}/events")
        self.assertEqual(events[0]["previous_status"], "open")
        status, report, headers = await call(self.app, "GET", "/api/v1/export")
        self.assertEqual(status, 200)
        self.assertEqual(report["scan"]["summary"]["failed"], 16)
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
        status, _, _ = await call(self.app, "POST", "/api/v1/scans/import", raw=b"{}", headers={"content-type": "text/plain"})
        self.assertEqual(status, 415)
        status, _, _ = await call(self.app, "POST", "/api/v1/scans/import", raw=b"x" * (MAX_IMPORT_BYTES + 1))
        self.assertEqual(status, 413)

    async def test_cross_origin_writes_and_untrusted_hosts_rejected(self):
        status, _, _ = await call(self.app, "POST", "/api/v1/scans/demo", headers={"origin": "https://untrusted.example"})
        self.assertEqual(status, 403)
        status, _, _ = await call(self.app, "GET", "/api/v1/health", headers={"host": "untrusted.example"})
        self.assertEqual(status, 400)
        status, _, _ = await call(self.app, "POST", "/api/v1/scans/demo", headers={"origin": "http://127.0.0.1:5173"})
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
        second_app = create_app(Path(self.temp.name) / "api.db")
        async with second_app.router.lifespan_context(second_app):
            _, scans, _ = await call(second_app, "GET", "/api/v1/scans")
            self.assertEqual(len(scans), 1)

    @unittest.skipUnless((ROOT / "frontend/dist/index.html").exists(), "Build the frontend before checking static serving")
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
