# Phase 2 cloud collection and anomaly detection

Phase 2 extends the configuration prototype with provider collection and a real
unsupervised activity model. The user authorized this phase and selected
synthetic and mocked validation because no cloud accounts are configured.

## Implemented scope

| Deliverable | Implementation |
| --- | --- |
| Read-only cloud collection | AWS boto3 adapter; Azure Resource Manager and GCP REST adapters using local CLI tokens |
| Normalized activity | Typed events, UTC timestamp validation, account/principal boundaries, hourly aggregation |
| Activity feature pipeline | Event count, failure rate, distinct source IPs/regions, UTC off-hours ratio, sensitive-operation ratio |
| ML inference | Isolation Forest, calibrated threshold, score evidence, stable finding IDs, insufficient-data handling |
| Training and persistence | Normal-only fitting, separate calibration, versioned local artifacts, checksum validation, atomic publication |
| Evaluation | Held-out labels; precision, recall, F1, FPR, ROC AUC, confusion counts, fixed activity comparator |
| Application integration | Activity analysis, Model lab, Cloud connections, method and source labels, collection coverage |
| Compatibility | Existing SQLite schema and Phase 1 snapshots retained; optional events preserve old imports |
| Validation | Unit/API tests, AWS SDK stubs, mocked REST contracts, TypeScript and production builds |

## Acceptance evidence

The combined demo yields 16 configuration findings and three activity findings
from 18 resources and 330 events. All six windows are scored: three normal and
three anomalous. The ML-flagged demo windows do not trigger the fixed activity
comparator, demonstrating that scores are driven by the trained model.

The training dataset has 600 normal fitting rows, 200 normal calibration rows,
and 480 labeled evaluation rows. The threshold is set exclusively by the
calibration split. Evaluation contains 360 normal rows and 120 anomalies across
bursts, failed access, permission changes, and distributed access.

See `docs/model-evaluation.json` for measured results. Model recall is 25% at the
selected 98th-percentile threshold, below the comparator's 50.83%. The project
does not claim that ML outperforms that baseline or that the synthetic dataset
predicts real-world behavior.

## Phase boundary

This phase completes the local collection and ML implementation. Live-account
verification is unavailable by the user's selected validation scope. Collector
coverage is deliberately bounded and partial, and the synthetic-trained model
is experimental on live data.

Continuous monitoring, authenticated multi-user access, notifications, hosted
deployment, automatic remediation, complete provider policy evaluation, and
evaluation against real incidents remain future work.

## Upgrade

Install the updated backend requirements and restart the local server. Startup
loads or trains the model without contacting cloud services. Existing snapshots
remain unchanged. Run demo scan to create a combined Phase 2 snapshot.
