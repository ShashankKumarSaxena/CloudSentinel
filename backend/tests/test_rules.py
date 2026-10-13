import copy
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from backend.app.models import Inventory, Resource
from backend.app.rules import scan_resources

ROOT = Path(__file__).resolve().parents[2]


def resource(kind, config, **kwargs):
    return Resource.model_validate({"id": "test-resource", "name": "Test resource", "provider": "aws",
                                    "type": kind, "region": "test-region", "account": "test-account",
                                    "config": config, **kwargs})


class RulesTest(unittest.TestCase):
    def test_demo_baseline_is_reproducible(self):
        inventory = Inventory.model_validate_json((ROOT / "data/demo_inventory.json").read_text())
        result = scan_resources(inventory.resources)
        self.assertEqual(result["summary"], {"resources": 18, "total_checks": 30, "passed": 14,
                                              "failed": 16, "unknown": 0, "posture_score": 47})
        self.assertEqual({s: sum(f["severity"] == s for f in result["findings"]) for s in ("critical", "high", "medium")},
                         {"critical": 3, "high": 8, "medium": 5})
        self.assertEqual({f["provider"] for f in result["findings"]}, {"aws", "azure", "gcp"})

    def test_secure_inventory_has_no_findings(self):
        assets = [resource("storage", {"public_access": False, "encrypted": True}),
                  resource("identity", {"permissions": ["storage:read"], "admin": True, "mfa_enabled": True}, id="admin"),
                  resource("firewall", {"ingress_cidrs": ["10.0.0.0/8"], "ports": [22]}, id="network"),
                  resource("audit", {"logging_enabled": True}, id="logs")]
        result = scan_resources(assets)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["summary"]["posture_score"], 100)

    def test_missing_configuration_is_unknown_not_passed(self):
        result = scan_resources([resource("storage", {})])
        self.assertEqual(result["summary"]["unknown"], 2)
        self.assertEqual(result["summary"]["passed"], 0)
        self.assertIsNone(result["summary"]["posture_score"])
        self.assertEqual(result["findings"], [])

    def test_unknown_fields_excluded_from_score(self):
        result = scan_resources([resource("storage", {"public_access": False})])
        self.assertEqual(result["summary"]["posture_score"], 100)
        self.assertEqual(result["summary"]["unknown"], 1)

    def test_non_privileged_workload_does_not_require_mfa(self):
        result = scan_resources([resource("identity", {"admin": False, "permissions": ["storage:read"]})])
        self.assertEqual(result["summary"]["unknown"], 0)
        self.assertEqual(result["findings"], [])

    def test_ipv6_world_access_and_all_ports_are_detected(self):
        result = scan_resources([resource("firewall", {"ingress_cidrs": ["::/0"], "ports": [0]})])
        self.assertEqual(result["findings"][0]["rule_id"], "NET-001")

    def test_public_https_is_not_a_management_port_issue(self):
        result = scan_resources([resource("firewall", {"ingress_cidrs": ["0.0.0.0/0"], "ports": [443]})])
        self.assertEqual(result["findings"], [])

    def test_permission_wildcard_is_detected(self):
        result = scan_resources([resource("identity", {"admin": False, "permissions": ["storage:*"]})])
        self.assertEqual(result["findings"][0]["rule_id"], "IAM-001")

    def test_findings_are_stable_across_scans_and_unique_across_providers(self):
        assets = [resource("storage", {"public_access": True, "encrypted": True}, provider=p) for p in ("aws", "azure", "gcp")]
        first, second = scan_resources(assets), scan_resources(assets)
        self.assertEqual(first, second)
        self.assertEqual(len({f["id"] for f in first["findings"]}), 3)


class ValidationTest(unittest.TestCase):
    def setUp(self):
        self.inventory = json.loads((ROOT / "data/demo_inventory.json").read_text())

    def test_duplicate_provider_resource_rejected(self):
        self.inventory["resources"].append(copy.deepcopy(self.inventory["resources"][0]))
        with self.assertRaises(ValidationError):
            Inventory.model_validate(self.inventory)

    def test_invalid_cidr_and_port_rejected(self):
        for config in ({"ingress_cidrs": ["not-a-cidr"]}, {"ports": [-1]}, {"ports": [65536]}):
            with self.subTest(config=config), self.assertRaises(ValidationError):
                resource("firewall", config)

    def test_string_boolean_and_extra_fields_rejected(self):
        for config in ({"public_access": "false"}, {"encryption": True}):
            with self.subTest(config=config), self.assertRaises(ValidationError):
                resource("storage", config)

    def test_empty_inventory_and_unsupported_version_rejected(self):
        for update in ({"resources": []}, {"schema_version": "2.0"}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                Inventory.model_validate(self.inventory | update)


if __name__ == "__main__":
    unittest.main()
