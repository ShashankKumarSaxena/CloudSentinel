"""Hosted-demo account bootstrap from secret environment values."""

from pathlib import Path
import tempfile
import unittest

from backend.app.repositories.store import Store
from backend.app.services.auth import AuthService
from scripts.bootstrap_hosted_demo import bootstrap

ADMIN = "test-only-admin-password"
VIEWER = "test-only-viewer-password"


class HostedDemoBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.auth = AuthService(Store(Path(self.temp.name) / "demo.db"))

    def tearDown(self):
        self.auth.store.database.close()
        self.temp.cleanup()

    def roles(self):
        return {user["username"]: user["role"] for user in self.auth.list_users()}

    def test_creates_admin_and_read_only_viewer_once(self):
        environ = {
            "CLOUDSENTINEL_DEMO_ADMIN_PASSWORD": ADMIN,
            "CLOUDSENTINEL_DEMO_VIEWER_PASSWORD": VIEWER,
        }
        self.assertEqual(bootstrap(self.auth, environ), ["admin", "viewer"])
        self.assertEqual(self.roles(), {"admin": "admin", "viewer": "viewer"})
        self.assertEqual(bootstrap(self.auth, environ), [])
        self.assertIsNotNone(self.auth.login("viewer", VIEWER, "127.0.0.1"))

    def test_fresh_database_requires_an_admin_password(self):
        with self.assertRaises(SystemExit):
            bootstrap(self.auth, {"CLOUDSENTINEL_DEMO_VIEWER_PASSWORD": VIEWER})
        self.assertEqual(self.roles(), {})

    def test_short_password_is_rejected_without_echoing_it(self):
        with self.assertRaises(SystemExit) as raised:
            bootstrap(self.auth, {"CLOUDSENTINEL_DEMO_ADMIN_PASSWORD": "short"})
        self.assertNotIn("short", str(raised.exception))
        self.assertEqual(self.roles(), {})


if __name__ == "__main__":
    unittest.main()
