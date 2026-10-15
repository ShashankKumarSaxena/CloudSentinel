# Activity model and dataset contract

The detector uses scikit-learn Isolation Forest to learn a normal feature
distribution and score independent hourly windows. Configuration checks remain
a separate deterministic baseline. The algorithm and score interpretation follow
the [scikit-learn documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html).
CloudSentinel negates `score_samples`: larger values mean more unusual behavior.
Scores are not attack probabilities or calibrated confidence.

## Features

Events group by provider, account, principal, and UTC hour. The feature version
is `activity-hour-v1`. Configuration snapshots do not produce ML features.

| Feature | Meaning | Transform |
| --- | --- | --- |
| event_count | Observed events in the hour | log1p |
| failure_rate | Explicit failures / all events; null if any outcome is unknown | Identity |
| distinct_ips | Distinct recorded source addresses; null if any is missing | log1p |
| distinct_regions | Distinct recorded event region labels | log1p |
| off_hours_rate | Share of events in 22:00–05:59 UTC | Identity |
| sensitive_rate | Share of normalized sensitive operations; null if any flag is unknown | Identity |

Only complete windows with at least five events are scored. Missing fields are
not imputed as safe. Region labels are provider metadata, not verified geographic
locations. Source fields may contain provider service strings; distinct values
are counted as metadata, not geolocation. UTC off-hours is a feature, not a policy;
legitimate batch activity appears in the normal synthetic data.

Deviation signals compare transformed values with the training median and
5th–95th-percentile width. They are review aids, not causal feature attributions.

## Training and calibration

Parameters: 200 trees, max_samples up to 256, random_state 42, n_jobs 1, and
contamination auto. Only normal training features enter `fit`. Labels, scenarios,
provider IDs, principal IDs, and timestamps are excluded.

The threshold is the 98th percentile of scores on a separate normal calibration
split. This is a conservative operating point, not a guarantee of 2% false
positives in new data. Evaluation labels cannot influence the fit or threshold.
No parameters were tuned against the evaluation labels.

## JSON training contract

In demo mode, administrators can upload JSON in Model lab or POST to
`/api/v1/model/train` (maximum 2 MB). Production disables API training.
Train reviewed data offline and install only trusted local artifacts into the
worker model volume during a maintenance window. Live ML is off by default;
`CLOUDSENTINEL_LIVE_ML_ENABLED=1` requires a ready artifact with `user_labeled`
provenance. This field is an operator assertion, not a quality certification.
The CLI is `python3 scripts/train_model.py --dataset /path/to/dataset.json`.
Serialized models and executable pickle uploads are not accepted.

```json
{
  "name": "Reviewed hourly activity",
  "provenance": "user_labeled",
  "train": [],
  "calibration": [],
  "evaluation": []
}
```

The abbreviated empty lists show structure only. Actual input needs 100–5,000
training samples, 50–5,000 calibration samples, and 50–5,000 evaluation samples.
Each sample has this shape:

```json
{
  "id": "sample-001",
  "features": {
    "event_count": 30,
    "failure_rate": 0.03333333333333333,
    "distinct_ips": 2,
    "distinct_regions": 1,
    "off_hours_rate": 0.0,
    "sensitive_rate": 0.03333333333333333
  },
  "label": "normal",
  "scenario": "reviewed_business_activity"
}
```

Training/calibration require normal labels. Evaluation needs both `normal` and
`anomaly`. IDs and feature rows must be unique across and within splits. Missing
features, invalid ranges, extra fields, and infeasible counts are rejected.
Provenance is `synthetic` or `user_labeled`; user labels are supplied assertions,
not independently verified incidents. Use `data/ml/synthetic_dataset.json` as
the full example. Prepare reviewed local windows with independent time/principal
splits. The application does not label real incidents for you.

## Persistence

Application-generated joblib artifacts live in `.runtime/models/`, outside Git.
Metadata records model ID, feature/runtime versions, dataset hash, parameters,
threshold, and evaluation. Atomic replacement publishes completed artifacts.
In demo mode, a missing/incompatible artifact is replaced by the bundled default
on startup. Production never automatically trains a synthetic fallback; invalid
artifacts prevent ML-enabled startup. With live ML disabled, configuration checks
remain available without loading a model.
Invalid training input never replaces the active model. Do not manually place
untrusted joblib files in the local model directory.

`scripts/generate_ml_data.py` uses seed 20261014 for reproducible synthetic data.
`scripts/train_model.py` writes the model and evaluation report. Scores and metrics
repeat in the pinned runtime; version IDs and timestamps change. Retraining only
affects new scans, preserving old evidence and model metadata. Restart a running
server after CLI training; Model lab retraining updates the active process immediately.

## Measured limitations

The 480-row holdout includes 360 normal rows and 120 anomalies. Isolation Forest
detects 30 anomalies, misses 90, and flags eight normal rows. Precision is 78.95%,
recall 25%, F1 37.97%, FPR 2.22%, and ROC AUC 0.8684.

The comparator detects 61 anomalies, misses 59, and flags eight normal rows.
It flags failure_rate >= .5, event_count >= 150, or sensitive_rate >= .5.
It is an activity comparator, not the configuration scanner. No model performance
advantage is claimed at this threshold.

The six-window application fixture is separate from evaluation. Its three unusual
windows combine source/region diversity and sensitive activity. Passing it is
integration evidence, not a general accuracy benchmark. Real-world accuracy
requires independent labeled data from actual accounts.
