from pathlib import Path
import tempfile
import unittest

from backend.app.models import Inventory
from backend.app.store import Store

ROOT = Path(__file__).resolve().parents[2]


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.store = Store(self.path)
        self.inventory = Inventory.model_validate_json((ROOT / "data/demo_inventory.json").read_text())

    def tearDown(self):
        self.temp.cleanup()

    def test_scans_persist_across_restarts_and_latest_is_correct(self):
        first = self.store.scan(self.inventory, "demo")
        second = self.store.scan(self.inventory, "import")
        reopened = Store(self.path)
        self.assertEqual(reopened.get_scan()["id"], second["id"])
        self.assertEqual(reopened.get_scan(first["id"])["source"], "demo")
        self.assertEqual(len(reopened.list_scans()), 2)

    def test_triage_is_persistent_and_does_not_change_scan_evidence(self):
        first = self.store.scan(self.inventory, "demo")
        finding = first["findings"][0]
        self.store.triage(finding["id"], "acknowledged")
        self.store.triage(finding["id"], "resolved")
        result = Store(self.path).get_scan(first["id"])
        self.assertEqual(result["summary"], first["summary"])
        self.assertEqual(result["findings"][0]["evidence"], finding["evidence"])
        self.assertEqual(result["findings"][0]["status"], "resolved")
        self.assertEqual(self.store.events(finding["id"])[0]["previous_status"], "acknowledged")
        self.assertEqual(len(self.store.events(finding["id"])), 2)

    def test_status_survives_rescan_with_same_fingerprint(self):
        first = self.store.scan(self.inventory, "demo")
        self.store.triage(first["findings"][0]["id"], "acknowledged")
        second = self.store.scan(self.inventory, "demo")
        self.assertEqual(second["findings"][0]["status"], "acknowledged")

    def test_unknown_scan_and_finding_return_none(self):
        self.assertIsNone(self.store.get_scan())
        self.assertIsNone(self.store.get_scan("missing"))
        self.assertIsNone(self.store.triage("missing", "resolved"))
        self.store.scan(self.inventory, "demo")
        self.assertIsNone(self.store.triage("' OR 1=1 --", "resolved"))


if __name__ == "__main__":
    unittest.main()
