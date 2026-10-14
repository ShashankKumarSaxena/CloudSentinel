"""Isolation Forest with separate calibration and held-out evaluation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
from uuid import uuid4

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score, roc_auc_score

from .activity import FEATURE_NAMES
from .models import ActivityFeatures, TrainingDataset

ROOT = Path(__file__).resolve().parents[2]
FEATURE_VERSION = "activity-hour-v1"


def vector(features: dict) -> list[float]:
    return [float(np.log1p(features[name])) if name in {"event_count", "distinct_ips", "distinct_regions"}
            else float(features[name]) for name in FEATURE_NAMES]


def activity_baseline(features: dict) -> bool:
    """Fixed activity comparator; configuration checks are evaluated separately."""
    return features["failure_rate"] >= .5 or features["event_count"] >= 150 or features["sensitive_rate"] >= .5


def metrics(labels, predicted, scores=None) -> dict:
    tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
    return {"precision": round(float(precision_score(labels, predicted, zero_division=0)), 4),
            "recall": round(float(recall_score(labels, predicted, zero_division=0)), 4),
            "f1": round(float(f1_score(labels, predicted, zero_division=0)), 4),
            "false_positive_rate": round(float(fp / (fp + tn)), 4),
            "true_positive": int(tp), "false_positive": int(fp), "true_negative": int(tn), "false_negative": int(fn),
            "roc_auc": round(float(roc_auc_score(labels, scores)), 4) if scores is not None else None}


class ModelService:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.artifact = None
        pointer = directory / "active.json"
        if pointer.exists():
            # Only this application's local artifacts are loadable. No upload path.
            try:
                metadata = json.loads(pointer.read_text())
                filename = metadata["filename"]
                if Path(filename).name != filename or not filename.endswith(".joblib"):
                    raise ValueError("Invalid model artifact name")
                model_path = directory / filename
                if hashlib.sha256(model_path.read_bytes()).hexdigest() != metadata["sha256"]:
                    raise ValueError("Model artifact checksum mismatch")
                if metadata["sklearn_version"] != sklearn.__version__ or metadata["feature_version"] != FEATURE_VERSION:
                    raise ValueError("Model runtime or feature version mismatch")
                self.artifact = joblib.load(model_path)
            except (KeyError, ValueError, OSError, EOFError):
                self.artifact = None

    def ensure_default(self):
        with self.lock:
            if self.artifact is None:
                dataset = TrainingDataset.model_validate_json((ROOT / "data/ml/synthetic_dataset.json").read_text())
                self.train(dataset)

    def status(self) -> dict:
        with self.lock:
            if self.artifact is None:
                return {"ready": False, "algorithm": "Isolation Forest", "feature_version": FEATURE_VERSION}
            return {"ready": True, **self.artifact["metadata"]}

    def train(self, dataset: TrainingDataset) -> dict:
        # Train and evaluate off to the side; publish only a complete artifact.
        training = np.asarray([vector(s.features.model_dump()) for s in dataset.train], dtype=np.float64)
        calibration = np.asarray([vector(s.features.model_dump()) for s in dataset.calibration], dtype=np.float64)
        evaluation = np.asarray([vector(s.features.model_dump()) for s in dataset.evaluation], dtype=np.float64)
        model = IsolationForest(n_estimators=200, max_samples=min(256, len(training)), random_state=42,
                                contamination="auto", n_jobs=1)
        model.fit(training)
        threshold = float(np.quantile(-model.score_samples(calibration), .98))
        scores = -model.score_samples(evaluation)
        predicted = scores > threshold
        labels = np.asarray([s.label == "anomaly" for s in dataset.evaluation], dtype=int)
        baseline = [activity_baseline(s.features.model_dump()) for s in dataset.evaluation]
        model_id = "iforest-" + str(uuid4())[:8]
        per_scenario = {}
        for scenario in sorted({s.scenario for s in dataset.evaluation}):
            indices = [i for i, s in enumerate(dataset.evaluation) if s.scenario == scenario]
            per_scenario[scenario] = {"samples": len(indices), "flagged": int(sum(predicted[indices])),
                                      "actual_anomalies": int(sum(labels[indices]))}
        metadata = {"id": model_id, "algorithm": "Isolation Forest", "type": "unsupervised anomaly detection",
                    "feature_version": FEATURE_VERSION, "features": list(FEATURE_NAMES), "sklearn_version": sklearn.__version__,
                    "created_at": datetime.now(timezone.utc).isoformat(), "dataset": dataset.name,
                    "provenance": dataset.provenance, "threshold": round(threshold, 6),
                    "calibration_quantile": .98, "training_samples": len(training),
                    "calibration_samples": len(calibration), "evaluation_samples": len(evaluation),
                    "dataset_sha256": hashlib.sha256(dataset.model_dump_json().encode()).hexdigest(),
                    "parameters": {"n_estimators": 200, "max_samples": min(256, len(training)), "random_state": 42},
                    "evaluation": {"model": metrics(labels, predicted, scores), "activity_baseline": metrics(labels, baseline),
                                   "scenarios": per_scenario},
                    "notice": "Synthetic evaluation does not establish real-world detection accuracy. Scores are not probabilities. Retrain on reviewed local normal activity before relying on live results."}
        artifact = {"model": model, "threshold": threshold, "metadata": metadata,
                    "medians": np.median(training, axis=0), "q05": np.quantile(training, .05, axis=0),
                    "q95": np.quantile(training, .95, axis=0)}
        with self.lock:
            filename = f"{model_id}.joblib"
            temporary = self.directory / f".{model_id}.tmp"
            joblib.dump(artifact, temporary)
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            temporary.replace(self.directory / filename)
            (self.directory / filename).chmod(0o600)
            pointer = {"filename": filename, "sha256": digest, "sklearn_version": sklearn.__version__, "feature_version": FEATURE_VERSION}
            pending = self.directory / f".{model_id}.json"
            pending.write_text(json.dumps(pointer))
            pending.replace(self.directory / "active.json")
            (self.directory / "active.json").chmod(0o600)
            self.artifact = artifact
        return self.status()

    def score(self, windows: list[dict]) -> tuple[list[dict], list[dict], dict]:
        with self.lock:
            artifact = self.artifact
        if artifact is None:
            raise RuntimeError("The activity model is not ready. Train it before scanning.")
        normalized = []
        complete = {}
        for index, window in enumerate(windows):
            values = ActivityFeatures.model_validate(window["features"]).model_dump()
            missing = [key for key, value in values.items() if value is None]
            normalized.append((values, missing))
            if not missing and values["event_count"] >= 5:
                complete[index] = vector(values)
        # Batch inference keeps bounded imports responsive even with many principals.
        scores = dict(zip(complete, -artifact["model"].score_samples(np.asarray(list(complete.values()))))) if complete else {}
        width = np.maximum(artifact["q95"] - artifact["q05"], .05)
        results, findings = [], []
        for index, window in enumerate(windows):
            values, missing = normalized[index]
            if missing or values["event_count"] < 5:
                results.append(window | {"status": "insufficient_data", "missing_features": missing,
                                         "score": None, "threshold": artifact["threshold"], "signals": []})
                continue
            row = np.asarray(complete[index])
            score = float(scores[index])
            flagged = score > artifact["threshold"]
            deviations = np.abs(row - artifact["medians"]) / width
            top = np.argsort(deviations)[::-1][:3]
            # Baseline deviations aid review; these are not causal feature attributions.
            signals = [{"feature": FEATURE_NAMES[i], "value": values[FEATURE_NAMES[i]],
                        "baseline_deviation": round(float(deviations[i]), 3)} for i in top]
            result = window | {"status": "anomaly" if flagged else "normal", "score": round(score, 6),
                               "threshold": round(artifact["threshold"], 6), "signals": signals, "missing_features": []}
            results.append(result)
            if flagged:
                fid = hashlib.sha256(f"ml:{FEATURE_VERSION}:{window['id']}".encode()).hexdigest()[:24]
                findings.append({"id": fid, "rule_id": "ML-ACT-001", "title": "Unusual cloud activity pattern",
                                 "severity": "medium", "category": "Activity anomaly", "detection_method": "ml",
                                 "resource_id": window["principal"], "resource_name": window["principal"],
                                 "resource_type": "identity", "provider": window["provider"], "region": "activity window",
                                 "account": window["account"], "description": "Isolation Forest flagged this hourly activity window as unusual relative to its training baseline. This is a review signal, not proof of an attack.",
                                 "remediation": "Review the principal's audit events, validate the source addresses and operations, and confirm whether the activity was expected. Investigate unexpected access with your incident response process.",
                                 "evidence": {"window_start": window["window_start"], "model_id": artifact["metadata"]["id"],
                                              "score": result["score"], "threshold": result["threshold"], "features": values,
                                              "signals": signals, "actions": window["actions"]}})
        return results, findings, artifact["metadata"]
