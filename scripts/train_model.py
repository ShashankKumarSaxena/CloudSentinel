"""Train from a validated JSON dataset and publish a local versioned artifact."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.ml import ModelService
from backend.app.models import TrainingDataset

parser = argparse.ArgumentParser()
parser.add_argument("--dataset", type=Path, default=ROOT / "data/ml/synthetic_dataset.json")
parser.add_argument("--output-dir", type=Path, default=ROOT / ".runtime/models")
parser.add_argument("--report", type=Path, default=ROOT / "docs/model-evaluation.json")
args = parser.parse_args()
dataset = TrainingDataset.model_validate_json(args.dataset.read_text())
status = ModelService(args.output_dir).train(dataset)
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(status, indent=2) + "\n")
print(json.dumps({"model_id": status["id"], "provenance": status["provenance"],
                  "evaluation": status["evaluation"], "report": str(args.report)}, indent=2))
