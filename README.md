# CloudSentinel

**A local multi-cloud security workspace with configuration checks and activity anomaly detection.**

CloudSentinel reviews AWS, Azure, and GCP configuration and activity snapshots.
It combines six explainable configuration checks with an **Isolation Forest**
model, preserves evidence in SQLite, and provides resource inspection, finding
triage, activity review, model evaluation, and JSON reports.

Phase 1 established the configuration baseline. **Phase 2 adds read-only cloud
collectors, event normalization, hourly features, ML inference, training, and
held-out evaluation.** Live-account collection has not been verified: this
release was tested with synthetic data and mocked provider APIs because no cloud
accounts were configured.

## Run locally

Requires Python 3.12+ and Node.js 22.12+ with npm. Node 24 is recommended.

```bash
bash scripts/setup.sh
bash scripts/demo.sh
```

Open **http://127.0.0.1:8000**. The same server serves the dashboard and API;
API documentation is at **http://127.0.0.1:8000/docs**. Dependencies need internet
access for their initial installation. The installed synthetic workflow runs
offline without cloud credentials or a separate database.

If the application was already running before the Phase 2 upgrade, stop it with
Ctrl+C, install the updated backend requirements, and restart it. Existing scans
are preserved. Click **Run demo scan** to create a Phase 2 snapshot with activity.

For frontend development:

```bash
bash scripts/dev.sh
# Dashboard: http://127.0.0.1:5173
# API:       http://127.0.0.1:8000
```

## Workspace capabilities

| Area | Behavior |
| --- | --- |
| Overview | Computed counts, configuration posture, severity distribution, and activity summary |
| Security findings | Configuration and ML findings with method labels, evidence, remediation, and persistent triage |
| Cloud inventory | Resource search, provider filters, normalized configuration, and applicable check outcomes |
| Activity analysis | Hourly windows, model scores, missing-data handling, feature evidence, and deviation signals |
| Model lab | Versioned model metadata, separate data splits, held-out metrics, and retraining from validated JSON |
| Cloud connections | Opt-in read-only collection using local credentials; coverage and partial failures |
| Scan history | Immutable configurations, evidence, model version, activity results, and source labels |
| Reports | JSON exports with rules, ML evidence, provenance, and collection coverage |

The Phase 2 demo has **18 resources**, **30 configuration checks**, and **330
normalized events in six hourly windows**. It produces **16 configuration
findings and three ML anomaly findings**. Configuration posture remains **47%**
(14 passing checks out of 30). ML findings never alter that configuration score.

Sources are explicitly labeled `demo`, `import`, or `live`. Missing configuration
stays unknown. Activity windows with missing features or fewer than five events
are not scored. Resolving a finding records team triage, not verified remediation.

## Model and evaluation

The model is unsupervised Isolation Forest with 200 trees and a fixed random seed.
It fits 600 synthetic normal windows, calibrates its decision threshold on 200
separate normal windows, and evaluates against 480 held-out labeled windows.
Sample IDs and feature rows cannot overlap between splits. Labels and identifiers
are never input features.

| Metric on the synthetic holdout | Isolation Forest | Fixed activity baseline |
| --- | --- | --- |
| Precision | 78.95% | 88.41% |
| Recall | 25.00% | 50.83% |
| False-positive rate | 2.22% | 2.22% |
| F1 | 37.97% | 64.55% |

This evaluation **does not establish an accuracy improvement or real-world
performance**. The selected conservative threshold misses 90 of 120 labeled
anomalies. The model and configuration rules remain complementary review tools;
the activity comparator above is a separate fixed-threshold method evaluated on
the same activity labels. Model Lab exposes the misses and false positives.

Use a reviewed local activity dataset before relying on model alerts from live
accounts. Scores are not probabilities. See [docs/model.md](docs/model.md) and
the complete [evaluation report](docs/model-evaluation.json).

```bash
make train-model
# Train on another reviewed dataset:
python3 scripts/train_model.py --dataset /path/to/dataset.json
```

The default model trains automatically on first startup and persists under
`.runtime/models/`. A new model affects subsequent scans only; past snapshots
retain their original evidence and model metadata.

## Optional cloud collection

Configure read-only access locally, then use **Cloud connections** to collect a
snapshot. Credentials are never accepted in the dashboard, API, or inventory.

| Provider | Local authentication | Collection scope |
| --- | --- | --- |
| AWS | boto3 profile, environment, SSO, or role credential chain | Regional S3 buckets, security-group ingress, CloudTrail trails/events; global IAM users |
| Azure | Signed-in Azure CLI; subscription ID | Blob containers, network security groups, Azure Activity Log |
| GCP | Signed-in gcloud CLI; project ID | Storage buckets/IAM, VPC firewall rules, accessible Cloud Audit Logs |

Collectors expose unavailable and unsupported scopes. They do not fully evaluate
effective IAM, inherited organization controls, all firewall-policy interactions,
or provider-wide logging coverage. A partial snapshot is not a clean-account
result. See [docs/cloud-collectors.md](docs/cloud-collectors.md) for permissions,
mapping semantics, authentication, and limits.

## Imports and persistence

Use Cloud inventory → Import inventory for normalized JSON. Configuration-only
Phase 1 inventories remain compatible. Optional `events` adds activity analysis.
The examples are [data/demo_inventory.json](data/demo_inventory.json) and
[data/demo_activity_inventory.json](data/demo_activity_inventory.json).
The contract is documented in [docs/inventory-schema.md](docs/inventory-schema.md).

Imports are limited to 2 MB, 1,000 resources, and 10,000 events. Failed imports or
collections preserve the latest valid snapshot. The default database is
`.runtime/cloudsentinel.db`; `CLOUDSENTINEL_DB` overrides its path. Current triage
dispositions are joined into historical views while scan evidence stays fixed.

Keep this local prototype on loopback: it has no multi-user authentication,
scheduled monitoring, hosted deployment, notifications, or automatic remediation.
Do not put credentials or unnecessary personal data in snapshots.

## Validation

```bash
make check
# With the local application already running:
make smoke
```

Tests exercise normalization, leakage prevention, model persistence, inference,
configuration checks, provider mapping, bounded pagination, API flows, and error
handling. They use temporary databases, local models, AWS SDK stubs, and mocked
REST responses. See [docs/validation.md](docs/validation.md) for verified results
and remaining runtime/visual limits. GitHub Actions runs backend and build checks.

## Structure

```text
backend/app/           API, models, rules, activity pipeline, ML, SQLite
backend/app/collectors AWS SDK and Azure/GCP REST adapters
backend/tests/         Rule, API, model, provider, and persistence tests
frontend/src/          React dashboard, Activity analysis, Model lab, connections
data/                  Synthetic configuration and activity fixtures
data/ml/               Disjoint synthetic training/calibration/evaluation data
docs/                  Scope, architecture, model, provider contracts, validation
scripts/               Setup, local servers, training, generation, smoke checks
.github/workflows/     CI configuration
AGENTS.md              Project instructions and Phase 2 boundary
```

The original abstract is preserved in the root. See
[Phase 1 scope](docs/phase-1.md), [Phase 2 scope](docs/phase-2.md),
[architecture](docs/architecture.md), and [configuration rules](docs/rules.md).

## Git

The local repository is initialized and its `origin` points to
`https://github.com/ShashankKumarSaxena/CloudSentinel.git`.
Phase 2 source changes are ready for review; this implementation session has not
committed or pushed them. Dependencies, databases, local model artifacts,
credentials, environment files, and generated builds are ignored.
