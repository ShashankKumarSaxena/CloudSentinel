# CloudSentinel

**A self-hosted cloud security workspace for one organization, with a separate offline demo.**

CloudSentinel collects approved AWS, Azure, and GCP configuration and activity,
checks a focused security baseline, and gives your team evidence, account-scoped
snapshots, triage, alerts, scheduled monitoring, and exportable reports. Cloud
access is read-only. Credentials stay on the worker and never enter the browser.

The deployment package includes PostgreSQL, a dedicated collection worker, an
HTTPS proxy, role-based access, optional corporate OIDC sign-in, versioned schema
migrations, and backup/restore tools. This release is ready for deployment
verification: **live cloud access, PostgreSQL runtime, OIDC, and container execution
have not been verified in this environment**. See [validation](docs/validation.md)
for completed checks and rollout gates.

## Run the offline demo

Requires Python 3.12+ and Node.js 22.12+ with npm. Installation needs network
access; the installed demo runs without cloud accounts.

```bash
bash scripts/setup.sh
make create-admin
make demo
```

Open **http://127.0.0.1:8000**. Create your administrator through the interactive
CLI; there is no default account or password. The demo has 18 resources, 30
configuration checks, 330 activity events, and 19 findings. Its data is labeled
synthetic. SQLite and model artifacts persist in `.runtime/`. To develop with
hot reload, use `make dev` and open http://127.0.0.1:5173.

Docker alternative:

```bash
docker compose up -d --build
docker compose exec cloudsentinel python scripts/manage_users.py create-admin
```

The root Compose file builds the **demo** target and binds to loopback. Production
uses a different Compose file, database, volumes, and configuration.

## Deploy for real cloud accounts

Follow the [production deployment guide](docs/deployment.md). It covers DNS/HTTPS,
private secret preparation, PostgreSQL TLS, account approval, workload identity,
bootstrap, optional SSO, and verification before enabling scheduled collection.
The setup package supports AWS SDK credentials/assumed roles, Azure managed or
workload identity, and GCP workload identity/ADC with optional impersonation.

Production starts empty. It does not seed fixtures, train a synthetic model,
collect an account at startup, or create schedules. An operator maintains the
read-only account registry; analysts can request only approved account/region
combinations. Jobs are persisted and remain inspectable across restarts.

## What the workspace provides

| Area | Capabilities |
| --- | --- |
| Cloud connections | Approved accounts, region selection, idempotent background jobs, progress, pending cancellation, coverage |
| Findings and inventory | Six explainable configuration rules, evidence, remediation guidance, search/filtering, account-scoped triage |
| Activity analysis | Hourly activity windows and optional Isolation Forest anomaly scoring |
| Monitoring | Administrator-managed schedules, durable run history, retries, singleton worker ownership |
| Alert inbox | Finding recurrence, coverage/failure alerts, acknowledgment, optional TLS SMTP delivery |
| Team and access | Viewer/analyst/admin roles, local recovery administrator, optional pre-approved OIDC identities |
| History and reports | Immutable scan evidence, current dispositions, provenance, JSON exports |
| Operations | Readiness checks, structured request logs, migrations, private backups, explicit retention maintenance |

All users belong to one shared organization and can inspect its cloud evidence.
Roles restrict actions; there is no tenant or account-level visibility partition.
Resolving a finding records team review. A later explicit failing configuration
check can reopen it; a missing observation never proves remediation.

## Detection boundaries

This is a focused configuration and activity detector. The [rule catalog](docs/rules.md)
and [collector coverage](docs/cloud-collectors.md) define what it evaluates.
Unsupported or unavailable observations stay unknown; partial coverage is never
a clean-account verdict. It does not provide exhaustive cloud policy evaluation,
CVE/package scanning, automatic remediation, or compliance certification.

Activity detection uses an **unsupervised Isolation Forest**, alongside the
configuration rules. Live ML is **off by default**. Enabling it requires a reviewed
local model marked `user_labeled`; that provenance field is an operator assertion,
not independent validation. The bundled synthetic holdout has 78.95% precision,
25.00% recall, and 2.22% false-positive rate. Its fixed comparator has higher recall.
These metrics do not establish real-account performance. See the
[model contract](docs/model.md) and [evaluation](docs/model-evaluation.json).

## Maintain and verify

```bash
bash scripts/setup.sh --dev
make format
make check
make docker-config
# With a local server running:
make smoke
.venv/bin/python scripts/smoke_test.py --authenticated
```

The current session could not install new production/developer dependencies.
Python was formatted with Black 24.10.0 and frontend source with an available
Prettier 2.5.1. The package pins Prettier 3.6.2 for future development; run
`make format` and `make check` after installation. Its new lock entry has no
registry integrity hash because registry access was unavailable; refresh and
review the lockfile with `npm --prefix frontend install --package-lock-only`
before release. Existing runtime dependency checksums are preserved.

See [contributing](CONTRIBUTING.md), [architecture](docs/architecture.md),
[security](docs/security.md), and [operations](docs/operations.md).

```text
backend/app/
  api/                 Routes, contracts, access policy, HTTP boundaries
  core/                Validated settings and paths
  domain/              Typed inputs, account scopes, rules, activity features
  services/            Authentication, scan orchestration, jobs, monitoring, ML
  repositories/        Transactional evidence persistence
  infrastructure/      Provider adapters, credentials, databases, migrations, email
frontend/src/
  app/                 Application shell and navigation
  features/            Views grouped by product capability
  shared/              API client, contracts, reusable UI
  styles/              Design system and responsive styling
config/                Disabled account examples and read-only permission templates
deploy/production/     PostgreSQL, worker, API, HTTPS and identity overlays
scripts/               Setup, operator commands, backup, retention, verification
backend/tests/         Unit, API, mocked provider and optional integration checks
```

The original abstract and [phase records](docs/phase-3.md) remain as implementation
history. The local repository is initialized; connecting/pushing GitHub remains
your deferred step. This update has not been committed or published.
