"""Generate the reproducible synthetic dataset and normalized activity fixture."""
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.models import TrainingDataset, Inventory


def sample(rng, sample_id, scenario):
    count = int(rng.integers(15, 70))
    failure = float(rng.uniform(.005, .12))
    sensitive = float(rng.uniform(.005, .08))
    ips, regions = int(rng.choice([1, 2, 3])), int(rng.choice([1, 1, 1, 2]))
    off_hours = float(rng.choice([0, 0, 0, 0, 1]))
    if scenario == "legitimate_batch":
        count = int(rng.integers(80, 180))
        off_hours = 1.0
    elif scenario == "request_burst":
        count = int(rng.integers(250, 800))
    elif scenario == "failed_access":
        failure = float(rng.uniform(.6, .95))
        ips = int(rng.integers(5, 16))
    elif scenario == "permission_changes":
        sensitive = float(rng.uniform(.25, .45))
        ips = int(rng.integers(3, 8))
    elif scenario == "distributed_access":
        ips, regions = int(rng.integers(8, 20)), int(rng.integers(4, 9))
    features = {"event_count": count, "failure_rate": int(rng.binomial(count, failure)) / count,
                "distinct_ips": ips, "distinct_regions": regions, "off_hours_rate": off_hours,
                "sensitive_rate": int(rng.binomial(count, sensitive)) / count}
    return {"id": sample_id, "features": features,
            "label": "normal" if scenario in {"normal", "legitimate_batch"} else "anomaly", "scenario": scenario}


def generate():
    rng = np.random.default_rng(20261014)
    dataset = {"name": "Synthetic hourly cloud activity v1", "provenance": "synthetic"}
    feature_rows = set()
    for split, count in (("train", 600), ("calibration", 200), ("evaluation", 480)):
        rows = []
        for index in range(count):
            if split == "evaluation" and index >= 360:
                scenario = ["request_burst", "failed_access", "permission_changes", "distributed_access"][index % 4]
            else:
                scenario = "legitimate_batch" if index % 15 == 0 else "normal"
            while True:
                row = sample(rng, f"{split}-{index:04d}", scenario)
                fingerprint = json.dumps(row["features"], sort_keys=True)
                if fingerprint not in feature_rows:
                    feature_rows.add(fingerprint)
                    rows.append(row)
                    break
        dataset[split] = rows
    TrainingDataset.model_validate(dataset)
    output = ROOT / "data/ml"
    output.mkdir(parents=True, exist_ok=True)
    (output / "synthetic_dataset.json").write_text(json.dumps(dataset, indent=2) + "\n")

    inventory = json.loads((ROOT / "data/demo_inventory.json").read_text())
    events = []
    for provider in ("aws", "azure", "gcp"):
        for suspicious, count in ((False, 30), (True, 80)):
            principal = f"{provider}-{'platform-admin' if suspicious else 'build-service'}"
            for index in range(count):
                action = "DeleteResource" if suspicious and index % 3 == 0 else "ReadResource"
                events.append({"id": f"{provider}-{'anomaly' if suspicious else 'normal'}-{index:03d}",
                               "provider": provider, "account": f"sandbox-{provider}", "principal": principal,
                               "timestamp": f"2026-10-14T{'02' if suspicious else '10'}:{index % 60:02d}:00+00:00",
                               "action": action, "region": f"region-{index % (6 if suspicious else 1)}",
                               "source_ip": f"192.0.2.{1 + index % (15 if suspicious else 2)}",
                               "success": index % (4 if suspicious else 30) != 0,
                               "sensitive": action == "DeleteResource"})
    inventory["events"] = events
    Inventory.model_validate(inventory)
    (ROOT / "data/demo_activity_inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    print(f"Generated {sum(len(dataset[s]) for s in ('train', 'calibration', 'evaluation'))} dataset rows and {len(events)} demo events.")


if __name__ == "__main__":
    generate()
