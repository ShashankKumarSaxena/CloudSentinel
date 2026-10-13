# CloudSentinel

**Phase 1 of the AI-Based Automated Multi-Cloud Vulnerability Detector.**

A local cloud security workspace that turns AWS, Azure, and GCP configuration
snapshots into explainable findings. Review resources, inspect evidence and
remediation, track team dispositions, and preserve scan history in a polished
dashboard.

The supplied abstract does not define project phases. Phase 1 was agreed as a
working foundation and demo. This release implements that scope: **configuration
baseline checks using synthetic data or imported JSON snapshots**. Live cloud
collectors and ML anomaly detection remain future work.

## Run locally

Requires Python 3.12+ and Node.js 22.12+ (Node 24 recommended), with npm.

```bash
bash scripts/setup.sh
bash scripts/demo.sh
```

Open **http://127.0.0.1:8000**. The demo builds the dashboard and serves the UI and
API together. API documentation is available at **http://127.0.0.1:8000/docs**.
The first startup seeds one synthetic scan; later startups preserve your data.
No cloud accounts, credentials, paid services, or external database are required.
Internet access is needed for the initial dependency installation.

The dependencies are already installed in this workspace if setup was completed
during implementation; in that case `bash scripts/demo.sh` is sufficient.

For development with frontend refresh:

```bash
bash scripts/dev.sh
# Dashboard: http://127.0.0.1:5173
# API:       http://127.0.0.1:8000
```

## What Phase 1 delivers

| Capability | Working behavior |
| --- | --- |
| Security overview | Computed metrics, cloud inventory cards, severity distribution, priority findings |
| Findings | Search; cloud, severity, and status filters; configuration evidence; remediation guidance |
| Inventory | Provider-neutral resources, applicable check outcomes, configuration inspection |
| Baseline engine | Six deterministic checks for storage, permissions, MFA, ingress, and audit logging |
| Scan history | Immutable SQLite snapshots, timestamps, score, provenance, and scan detail |
| Team triage | Open, acknowledged, and resolved dispositions with a persistent audit trail |
| Imports | Strict schema validation; atomic scan creation; 2 MB / 1,000-resource limits |
| Reports | JSON export with provenance, evidence, current dispositions, and Phase 1 limitations |
| Project brief | In-app scope, architecture, delivered capabilities, and proposed future phases |

The shipped dataset contains **18 resources**, **30 checks**, and **16 findings**:
3 critical, 8 high, and 5 medium. Baseline posture is **47%**, the rounded pass rate
of 14 passing checks out of 30 evaluated checks. This is a baseline score, not a
compliance certification, ML confidence, detection accuracy, or probability of compromise.

Acceptance criteria and project scope are documented in
[docs/phase-1.md](docs/phase-1.md).

## Validation

```bash
make check
# With the local application already running:
make smoke
```

Backend tests use temporary databases and an in-process ASGI transport; they do
not require network ports or real cloud accounts. Type checking and the frontend
production build validate the dashboard source. See
[docs/validation.md](docs/validation.md) for actual verification results and limits.

## Structure

```text
backend/app/           API, typed schema, baseline rules, SQLite store
backend/tests/         Rule, validation, persistence, and API tests
frontend/src/          React + TypeScript dashboard and responsive styling
frontend/public/       Local static assets
data/                  Synthetic normalized multi-cloud inventory
docs/                  Phase scope, architecture, schema, validation
scripts/               Setup, demo, development, smoke test, Git initialization
.github/workflows/     Backend and frontend checks for GitHub Actions
AGENTS.md              Project instructions and Phase 1 boundary
```

## Configuration and data

The database defaults to `.runtime/cloudsentinel.db` and is ignored by Git.
Set `CLOUDSENTINEL_DB` in the shell to choose another database path. Imports follow
the contract in [docs/inventory-schema.md](docs/inventory-schema.md). The demo JSON
is a complete example. A new import becomes the latest inventory; Run demo scan
returns the latest view to the bundled synthetic inventory. Earlier snapshots remain.

Null or absent required configuration fields yield **unknown**, never a pass.
Unknown checks are excluded from the posture denominator and displayed separately.
Finding dispositions survive re-scans of the same provider/resource/rule.
Resolving a finding records team triage; it does not alter scan evidence or
verify a configuration change.

This release binds to the local machine and has no multi-user authentication.
Keep it on loopback for local use. Do not put credentials in inventory JSON.
There is no automatic remediation or connection to real cloud services.

## Initialize Git and connect GitHub later

```bash
bash scripts/init-git.sh
```

This initializes `main` and makes the first commit. Dependencies, databases,
environment files, credentials, and generated builds are ignored.

When your GitHub CLI login is ready:

```bash
gh auth login -h github.com
gh repo create Cloud-Vulnerability-Detector-MP --private --source=. --remote=origin --push
```

The implementation session could not write `.git`, and the saved GitHub CLI
token was invalid. The user chose to connect GitHub later. Run the local
initialization script in a normal terminal; no remote repository is claimed.

## Design and project notes

The dashboard uses a quiet green visual system, an accessible navigation drawer,
keyboard focus states, filters, empty/error states, and a responsive layout.
Assets and fonts use local or system resources so the installed demo works offline.
The source abstract is preserved unchanged in the project root.

See [docs/architecture.md](docs/architecture.md) for implementation decisions and
[docs/rules.md](docs/rules.md) for check semantics, references, and limitations.
