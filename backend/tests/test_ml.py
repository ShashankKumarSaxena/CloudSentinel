import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from pydantic import ValidationError

from backend.app.activity import aggregate
from backend.app.ml import ModelService, vector, activity_baseline
from backend.app.models import ActivityEvent, Inventory, TrainingDataset

ROOT = Path(__file__).resolve().parents[2]


class ActivityTest(unittest.TestCase):
    def event(self, **changes):
        return ActivityEvent.model_validate({"id": "e1", "provider": "aws", "account": "account", "principal": "identity",
            "timestamp": "2026-10-14T12:00:00+02:00", "action": "ReadResource", "source_ip": "192.0.2.1",
            "success": True, "sensitive": False, **changes})

    def test_hourly_aggregation_converts_to_utc_and_separates_accounts(self):
        first = self.event()
        second = self.event(id="e2", timestamp="2026-10-14T10:30:00Z", success=False)
        third = self.event(id="e3", account="other-account")
        windows = aggregate([first, second, third])
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0]["window_start"], "2026-10-14T10:00:00+00:00")
        self.assertEqual(windows[0]["features"]["event_count"], 2)
        self.assertEqual(windows[0]["features"]["failure_rate"], .5)

    def test_missing_event_evidence_remains_unknown(self):
        features = aggregate([self.event(success=None, source_ip=None, sensitive=None)])[0]["features"]
        for key in ("failure_rate", "distinct_ips", "sensitive_rate"):
            self.assertIsNone(features[key])

    def test_naive_or_invalid_timestamps_and_duplicate_events_rejected(self):
        for timestamp in ("2026-10-14T10:00:00", "not-a-timestamp"):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValidationError):
                self.event(timestamp=timestamp)
        inventory = json.loads((ROOT / "data/demo_activity_inventory.json").read_text())
        inventory["events"].append(inventory["events"][0])
        with self.assertRaises(ValidationError):
            Inventory.model_validate(inventory)


class ModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.model = ModelService(cls.directory)
        cls.dataset = TrainingDataset.model_validate_json((ROOT / "data/ml/synthetic_dataset.json").read_text())
        cls.status = cls.model.train(cls.dataset)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_threshold_uses_calibration_not_test_labels(self):
        artifact = self.model.artifact
        rows = np.asarray([vector(row.features.model_dump()) for row in self.dataset.calibration])
        expected = np.quantile(-artifact["model"].score_samples(rows), .98)
        self.assertEqual(artifact["threshold"], expected)
        self.assertEqual(self.status["training_samples"], 600)
        self.assertEqual(self.status["calibration_samples"], 200)
        self.assertEqual(self.status["evaluation_samples"], 480)
        self.assertEqual(self.status["provenance"], "synthetic")

    def test_demo_detects_three_anomalies_and_keeps_normal_windows(self):
        inventory = Inventory.model_validate_json((ROOT / "data/demo_activity_inventory.json").read_text())
        outcomes, findings, _ = self.model.score(aggregate(inventory.events))
        self.assertEqual(len(outcomes), 6)
        self.assertEqual(len(findings), 3)
        self.assertTrue(all(row["status"] == "anomaly" for row in outcomes if "admin" in row["principal"]))
        self.assertTrue(all(row["status"] == "normal" for row in outcomes if "build-service" in row["principal"]))
        self.assertTrue(all(f["detection_method"] == "ml" for f in findings))
        self.assertFalse(any(activity_baseline(row["features"]) for row in outcomes))

    def test_missing_features_and_tiny_windows_are_not_scored(self):
        inventory = Inventory.model_validate_json((ROOT / "data/demo_activity_inventory.json").read_text())
        windows = aggregate(inventory.events)
        windows[0]["features"]["failure_rate"] = None
        windows[1]["features"] = {"event_count": 1, "failure_rate": 0., "distinct_ips": 1,
                                   "distinct_regions": 1, "off_hours_rate": 0., "sensitive_rate": 0.}
        outcomes, _, _ = self.model.score(windows[:2])
        self.assertTrue(all(row["status"] == "insufficient_data" and row["score"] is None for row in outcomes))

    def test_model_persists_and_scoring_is_stable(self):
        reopened = ModelService(self.directory)
        self.assertEqual(reopened.status()["id"], self.status["id"])
        windows = aggregate(Inventory.model_validate_json((ROOT / "data/demo_activity_inventory.json").read_text()).events)
        self.assertEqual(self.model.score(windows), reopened.score(windows))

    def test_batch_inference_preserves_single_window_scores(self):
        windows = aggregate(Inventory.model_validate_json((ROOT / "data/demo_activity_inventory.json").read_text()).events)
        batch, _, _ = self.model.score(windows)
        for window, outcome in zip(windows, batch):
            single, _, _ = self.model.score([window])
            self.assertEqual(single[0], outcome)

    def test_corrupt_or_path_traversal_pointer_is_not_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "active.json").write_text(json.dumps({"filename": "../unsafe.joblib"}))
            self.assertFalse(ModelService(path).status()["ready"])

    def test_report_includes_misses_false_positives_and_comparator(self):
        report = self.status["evaluation"]
        for method in ("model", "activity_baseline"):
            counts = report[method]
            self.assertEqual(sum(counts[k] for k in ("true_positive", "false_positive", "true_negative", "false_negative")), 480)
            self.assertGreaterEqual(counts["false_positive_rate"], 0)
        self.assertGreater(report["model"]["false_negative"], 0)
        self.assertIn("permission_changes", report["scenarios"])


class DatasetValidationTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "data/ml/synthetic_dataset.json").read_text())

    def test_duplicate_identity_or_feature_rows_prevent_leakage(self):
        for field in ("id", "features"):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data["evaluation"][0][field] = data["train"][0][field]
                with self.assertRaises(ValidationError):
                    TrainingDataset.model_validate(data)

    def test_train_anomaly_missing_features_and_single_class_evaluation_rejected(self):
        datasets = []
        data = copy.deepcopy(self.data); data["train"][0]["label"] = "anomaly"; datasets.append(data)
        data = copy.deepcopy(self.data); data["train"][0]["features"]["failure_rate"] = None; datasets.append(data)
        data = copy.deepcopy(self.data)
        for row in data["evaluation"]: row["label"] = "normal"
        datasets.append(data)
        for data in datasets:
            with self.assertRaises(ValidationError):
                TrainingDataset.model_validate(data)
