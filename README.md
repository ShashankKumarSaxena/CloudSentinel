# CloudSentinel

**A local multi-cloud security workspace with configuration checks, activity anomaly detection, and scheduled monitoring.**

CloudSentinel reviews AWS, Azure, and GCP configuration and activity snapshots.
Six explainable configuration checks and an **Isolation Forest** anomaly model
produce separate findings, with evidence, triage, immutable history, and reports.
**Phase 3 adds required sign-in, administrator/analyst/viewer roles, persistent
monitoring schedules, an alert inbox, optional SMTP delivery, operational audit
records, backup/recovery tools, and a local Docker deployment package.**

Cloud collection is validated with synthetic data and mocked provider APIs.
No live-account validation is claimed. The Docker package has passed Compose
configuration validation; image build and container execution are pending the
user's Docker run. See [validation evidence](docs/validation.md).

## Run locally

Requires Python 3.12+ and Node.js 22.12+ with npm. Node 24 is recommended.

```bash
bash scripts/setup.sh
make create-admin
bash scripts/demo.sh
```

The administrator command prompts for a username and a password of 12–256
characters. There is no default account or password. Open
**http://127.0.0.1:8000** and sign in. The same server serves the dashboard and
API. On host installs, an offline API reference at `/docs` and request schemas
at `/openapi.json` are available after sign-in. Dependencies need
internet access for installation; the installed synthetic workflow runs offline.

For an existing Phase 1/2 install, stop the old server, install current
dependencies, create the first administrator, and restart. Existing snapshots
are preserved. Run a new demo scan to populate Phase 3 alerts; historical scans
are not backfilled into the inbox. Keep one server process per database.

```bash
bash scripts/dev.sh
# Dashboard: http://127.0.0.1:5173
# API:       http://127.0.0.1:8000
```

## Local Docker deployment

With Docker Desktop running, from the project root:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose exec cloudsentinel python scripts/manage_users.py create-admin
```

Open **http://127.0.0.1:8000** and sign in. First startup trains the bundled
synthetic model; allow it to finish before creating the administrator. The
container runs as a non-root user with a read-only root filesystem. SQLite and
models persist in the `cloudsentinel-data` named volume. The supplied port binds
to loopback and SMTP is disabled. If another server uses port 8000, stop it or
run `CLOUDSENTINEL_PORT=8001 docker compose up -d --build` and open port 8001.

See [deployment instructions](docs/deployment.md) for startup checks, mounted
credentials, overrides, recovery, and troubleshooting. No hosting service is
required or configured.

## Workspace capabilities

| Area | Behavior |
| --- | --- |
| Overview | Computed configuration posture, severity distribution, and activity summary |
| Security findings | Distinct rule/ML methods, evidence, remediation guidance, persistent triage |
| Cloud inventory | Search, provider filters, normalized configuration, applicable check outcomes |
| Activity analysis | Hourly windows, model scores, missing-data handling, feature evidence |
| Model lab | Versioned artifacts, separate data splits, held-out metrics; administrator retraining |
| Cloud connections | Opt-in read-only collection, coverage, and partial failures |
| Monitoring | Persisted demo/live schedules, enable/pause, manual run, retry backoff, run history |
| Alert inbox | Deduplicated finding/coverage/failure alerts, acknowledgment, delivery state and retries |
| Team & access | Administrator account management and audit log; own password changes and sign-out |
| Scan history & reports | Immutable evidence, provenance, model versions, current triage, JSON exports |

| Permission | Viewer | Analyst | Administrator |
| --- | --- | --- | --- |
| Inspect shared scans, alerts, schedules, models; export reports | Yes | Yes | Yes |
| Scan/import/collect; triage; acknowledge alerts | — | Yes | Yes |
| Manage accounts/schedules; train models; retry failed email; read audit log | — | — | Yes |
| Change own password and sign out | Yes | Yes | Yes |

This is one shared workspace. Roles restrict actions; they do not partition cloud
accounts or resource visibility. Authentication is always required for private
APIs. The first administrator is created only through the local CLI.
See [security design](docs/security.md).

The synthetic demo contains **18 resources**, **30 configuration checks**, and
**330 events in six hourly windows**. It produces **16 configuration findings
and three ML findings**. Configuration posture is **47%** (14/30 passing checks).
Repeated demo scans preserve history without repeating the same inbox alerts.

Sources are explicitly labeled `demo`, `import`, or `live`. Missing configuration
stays unknown. Windows with missing features or fewer than five events are not
scored. Acknowledgment records review; resolving a finding records triage rather
than verified remediation. No automatic cloud remediation is implemented.

## Model and evaluation

The model is **unsupervised Isolation Forest**, with 200 trees and a fixed random
seed. It fits 600 synthetic normal windows, calibrates the threshold on 200
separate normal windows, and evaluates on 480 held-out labeled windows. Sample
IDs and feature rows cannot overlap between splits. Labels/IDs are not features.

| Metric on the synthetic holdout | Isolation Forest | Fixed activity baseline |
| --- | --- | --- |
| Precision | 78.95% | 88.41% |
| Recall | 25.00% | 50.83% |
| False-positive rate | 2.22% | 2.22% |
| F1 | 37.97% | 64.55% |

These results **do not establish real-world performance or an accuracy
improvement**. The conservative threshold misses 90 of 120 labeled anomalies;
the fixed activity comparator has higher recall. Scores are not probabilities.
Review a local activity dataset before relying on live model alerts. See the
[model design](docs/model.md) and [evaluation report](docs/model-evaluation.json).

```bash
make train-model
# Local operator alternative for a reviewed dataset:
.venv/bin/python scripts/train_model.py --dataset /path/to/dataset.json
```

The default model trains on first startup and persists under `.runtime/models/`.
Retraining affects subsequent scans; historical model evidence stays fixed.

## Optional cloud collection

Configure read-only access locally, then use **Cloud connections**, or create an
explicit live schedule as an administrator. Startup, demo scans, and status
checks do not contact cloud accounts. No schedule exists by default.

| Provider | Authentication | Collection scope |
| --- | --- | --- |
| AWS | boto3 profile/environment/SSO/role chain | Regional S3, security groups, CloudTrail; global IAM users |
| Azure | Local Azure CLI or explicitly mounted token file | Blob containers, network security groups, Activity Log |
| GCP | Local gcloud CLI or explicitly mounted token file | Storage/IAM, VPC firewall rules, accessible Cloud Audit Logs |

The default Docker image includes boto3 and REST collectors, but does not include
Azure/gcloud CLIs. Containers can use administrator-configured read-only token
file mounts, with expiry managed locally. The browser never accepts cloud
credentials. [Collector documentation](docs/cloud-collectors.md) describes
permissions, mappings, and limits. Partial coverage is not a clean-account result.

## Persistence and operations

Normalized JSON imports are limited to 2 MB, 1,000 resources, and 10,000 events.
Configuration-only Phase 1 inventories remain compatible; optional `events`
adds activity scoring. See [inventory schema](docs/inventory-schema.md) and
[data/demo_activity_inventory.json](data/demo_activity_inventory.json).
Failed imports/collections preserve the latest valid scan.

Default state: `.runtime/cloudsentinel.db` and `.runtime/models/`.
`CLOUDSENTINEL_DB` changes the database path; the server uses a sibling `models/`
directory. Runtime files, mounted secrets, backups, and local overrides are
ignored by Git. Store backups securely: they contain sensitive workspace data
and password hashes, and are not encrypted.

```bash
.venv/bin/python scripts/backup.py backup backups/cloudsentinel.tar.gz
# Restore offline into a fresh directory, then launch using that database:
.venv/bin/python scripts/backup.py restore backups/cloudsentinel.tar.gz \
  --database .runtime-restored/cloudsentinel.db
```

Restoring removes sessions, pauses schedules, and suppresses pending email.
See [operations guide](docs/operations.md) for monitoring, optional SMTP,
deduplication, session recovery, and backup/restore procedures.

## Validation

```bash
make check
# With a server already running:
make smoke
.venv/bin/python scripts/smoke_test.py --authenticated
```

Tests cover rules, provider mapping, ML leakage/persistence, API authorization,
CSRF, expiry/revocation, concurrent schedule claims, crash recovery, alert
persistence/deduplication, mocked SMTP retries, and backup restoration. The
frontend passes TypeScript and production build checks. GitHub Actions is
configured for backend/frontend checks and a Docker startup smoke job; hosted
CI execution is not claimed. New pages still require browser click-through.

## Structure and scope

```text
backend/app/           FastAPI, auth, scan engine, rules, ML, monitoring, alerts
backend/app/collectors AWS SDK and Azure/GCP REST adapters
backend/tests/         Detection, access control, operations, and recovery tests
frontend/src/          React security workspace and sign-in
data/                 Synthetic configuration/activity fixtures and ML splits
docs/                 Scope, contracts, design, operations, deployment, evidence
scripts/               Setup, servers, training, account CLI, backup, smoke checks
Dockerfile             Multi-stage non-root application image
compose.yaml           Local deployment with persistent data volume
AGENTS.md              Project instructions and Phase 3 boundary
```

The abstract is preserved in the root. See [Phase 1](docs/phase-1.md),
[Phase 2](docs/phase-2.md), [Phase 3](docs/phase-3.md),
[architecture](docs/architecture.md), and [rules](docs/rules.md).
Distributed scheduling, hosted deployment, full provider policy evaluation,
automatic remediation, and real-incident model validation remain outside scope.

The local repository is initialized with origin
`https://github.com/ShashankKumarSaxena/CloudSentinel.git`. Phase 3 changes remain
local for review; this session did not commit or push them.
