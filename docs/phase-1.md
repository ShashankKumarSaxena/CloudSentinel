# Phase 1 working foundation and demo

> Historical implementation milestone. For current behavior and deployment, see
> [README](../README.md), [architecture](architecture.md), and [deployment](deployment.md).

The original abstract proposes a machine learning detector for AWS, Azure, and
GCP configuration and activity data. It does not specify phases. The user
confirmed that Phase 1 should be a working foundation and demo.

Phase 1 delivers a local prototype with a common configuration schema,
explainable deterministic checks, persistent scan snapshots, and a responsive
dashboard. It creates the data and application foundation for subsequent live
collection and anomaly detection.

## Requirements and acceptance criteria

| Abstract requirement | Phase 1 interpretation | Acceptance criterion |
| --- | --- | --- |
| Multi-cloud environments | Normalize synthetic or imported AWS/Azure/GCP snapshots | All three providers visible; same rules evaluate matching resource types |
| Collect configuration data | Fixture adapter and validated JSON importer | Inputs parsed through one typed schema; invalid imports do not change latest scan |
| Detect exposed storage | Public-access and encryption baseline | Failures include configuration evidence, severity, and suggested action |
| Detect weak permissions | Wildcard grants and privileged human MFA baseline | Known unsafe scenarios detected; absent fields stay unknown |
| Dashboard with severity | Overview, findings, inventory, and scan history | Live API responses drive all counts and details |
| Remediation suggestions | Explainable per-rule recommendations | Every finding includes evidence and guidance |
| Detect unusual activity using ML | Deferred until collection and training data exist | UI and reports do not claim ML or measured accuracy |
| Improve accuracy and false positives | Future evaluation objective | No unsupported benchmark or accuracy claim |

## Completed implementation

- FastAPI routes, bounded imports, provider-neutral Pydantic schema.
- Six baseline rules with stable provider/resource/rule fingerprints.
- SQLite snapshots, durable dispositions, and triage events.
- React and TypeScript dashboard with overview, filters, inspection drawers,
  inventory, historical snapshots, exports, and an in-app project brief.
- Synthetic dataset and reproducible baseline counts.
- Backend test suite, build checks, setup scripts, and GitHub Actions configuration.
- `AGENTS.md`, architecture, import contract, and setup instructions.

## Explicitly outside Phase 1

Live AWS, Azure, or GCP API collection; credential onboarding; cloud activity
ingestion; machine learning training or inference; automatic remediation;
scheduled scans; alerts; hosted deployment; multi-user authentication; full
provider policy evaluation; compliance certification.

## Completion and handoff

The implemented Phase 1 feature scope is complete. Validation status is recorded
in `docs/validation.md`, including outstanding visual and runtime checks.
Local Git initialization was prevented by the
session's read-only `.git` policy. `scripts/init-git.sh` performs it in the user's
terminal. The repository has since been initialized with an origin configured.

## Proposed later work

Phase 2 has now been implemented; see [docs/phase-2.md](phase-2.md).
Phase 3 has also been implemented; see [phase-3.md](phase-3.md).
The following records the original Phase 1 proposal.

Phase 2 should add least-privilege cloud collectors, clearly document mapping
from raw provider data into normalized fields, and create an activity feature
pipeline. Compare a trained anomaly model against the baseline using labeled
scenarios and report false positives, precision, recall, and evaluation limits.

A later hardening phase can add authenticated access, background jobs, alerts,
deployment, and continuous evaluation. These are proposed boundaries for future
planning, not supplied requirements or implemented capabilities.
