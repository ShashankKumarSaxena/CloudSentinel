# Phase 3 architecture

CloudSentinel is a local React dashboard backed by FastAPI and SQLite. A common
typed inventory schema lets the same checks evaluate resources across the three
providers. Phase 2 added read-only collection and activity scoring. Phase 3 adds
required authentication, durable scheduled execution, alerts, and local Docker
deployment. Startup and synthetic scans do not make cloud API calls.

```mermaid
flowchart LR
    A[Synthetic inventory JSON] --> C[Pydantic inventory validation]
    B[User imported JSON snapshot] --> C
    M[Opt-in AWS Azure GCP collectors] --> C
    C --> D[Provider neutral resource records]
    D --> E[Six configuration baseline rules]
    E --> F[Findings and check outcomes]
    D --> N[Hourly activity aggregation]
    N --> O[Isolation Forest inference]
    O --> F
    P[Normal training data] --> Q[Model training]
    R[Normal calibration data] --> Q
    S[Held-out labeled data] --> T[Model evaluation]
    Q --> T
    Q --> O
    F --> G[(SQLite immutable snapshots)]
    U[Local accounts and expiring sessions] --> V[Role and CSRF checks]
    V --> H[FastAPI API]
    W[Persisted monitor schedules] --> X[Single worker and durable claims]
    X --> M
    X --> A
    F --> Y[(Alert inbox and outbox)]
    Y --> Z[Opt-in TLS SMTP]
    G --> H
    H --> I[React security workspace]
    I --> J[JSON report]
    I --> K[Team disposition update]
    K --> L[(SQLite triage audit trail)]
    L --> H
```

## Data contracts

`backend/app/models.py` defines providers, configuration, inventory, events,
training data, and triage status. Inventory contains 1–1,000 resources with unique
IDs within each provider. Imports reject unknown keys, invalid CIDRs or ports,
string booleans, malformed JSON, and unsupported schema versions.

Configuration evidence represents normalized assertions, not full policy
evaluation. Collectors map supported settings conservatively and expose partial
coverage. Unknown fields remain unknown. No credential input is accepted.

## Rule evaluation

`backend/app/rules.py` evaluates only rules applicable to a resource's type.
An outcome is pass, fail, or unknown. Required missing fields yield unknown.
The exception is the MFA check for an explicitly non-admin identity: it passes
because the privileged-human rule is not violated.

Failed checks generate findings with a stable SHA-256-derived identifier from
provider, resource ID, and rule ID. Findings contain severity, category, affected
resource, evidence, and remediation. The severity is a project-defined baseline,
not CVSS or a vendor compliance score.

Posture is `round(passed / (passed + failed) × 100)`. It is null if all checks are
unknown. Coverage, passed/failed counts, and unknown counts remain visible.

## Persistence

`backend/app/activity.py` aggregates events by provider/account/principal/UTC hour.
`backend/app/ml.py` trains normal-only Isolation Forest models, calibrates a
threshold independently, and scores complete windows with at least five events.
Activity anomalies produce medium-severity review findings; they do not change
the configuration posture score. Model metadata and scores are saved in snapshots.

Versioned artifacts live under `.runtime/models/`. A completed model and its
pointer are published atomically. Model metadata includes feature/runtime
versions, dataset hash, parameters, threshold, provenance, and held-out metrics.
The upload contract is JSON data only; executable models cannot be uploaded.

`backend/app/store.py` saves the resource configurations, checks, findings, and
summary together in a SQLite transaction. The default database is under
`.runtime/` and excluded from Git. WAL mode and a connection timeout support
concurrent local reads and short writes.

Scan snapshots are immutable. Separate tables store finding dispositions and
triage events. Current dispositions are joined into historical responses, so
historical evidence and scores remain fixed while team review status remains
current. Repeated scans retain dispositions for identical finding fingerprints.

History lists the latest 100 records. The database retains older snapshots; there
is no retention cleanup, pagination beyond this list, or scan deletion.

## API and frontend

API routes are under `/api/v1`. An offline API reference is available at `/docs` after sign-in on host installs;
the Docker default disables it.
Imports read and bound the request stream before validation. Blocking scan and
SQLite work runs outside the async request loop. Mutations reject unrelated
browser origins, and the API accepts local hosts only. SQL uses placeholders.
Collection, scan, and training operations share a process-local mutation lock.
Failed imports, failed collection, and invalid training preserve valid state.

`/model` exposes metadata; `/model/train` accepts validated independent splits.
`/connectors` reports local configuration hints without making cloud API calls.
`/scans/collect` initiates the selected provider collector. All data includes
`demo`, `import`, or `live` provenance; the model has separate training provenance.

Activity analysis, Model lab, and Cloud connections extend the existing dashboard.
Historical Phase 1 snapshots are read compatibly without rewriting their evidence.

Vite proxies local development requests to port 8000. For local use,
`scripts/demo.sh` builds the frontend first, then FastAPI serves `frontend/dist/`
and the API on the same local origin. Navigation stays within the React app,
so there is no client-side URL routing or fallback dependency.

The interface provides focus states, labeled controls, empty/error messages,
reduced-motion support, and a responsive menu. Inspection dialogs close with
Escape, trap keyboard focus, and restore focus to their trigger.

## Authentication and operations

`auth.py` stores salted scrypt hashes, hashed opaque sessions, login attempt
windows, and user roles. The middleware protects private routes and enforces
CSRF/roles before request handlers. The first administrator is bootstrapped
locally. UI permissions mirror server permissions. See [security.md](security.md).

`engine.py` centralizes manual and scheduled scan/training operations. The
process-local mutation lock prevents competing collection or model changes.
`operations.py` creates scan alerts and audit records in the same transaction as
snapshot insertion. Schedule/run, alert review, delivery attempt, and account
records persist in SQLite alongside the existing immutable snapshots.

`monitoring.py` holds an exclusive file lock for one monitoring process per
database. A background thread claims due schedules transactionally, executes
bounded collections, records outcome/backoff, and drains optional email work.
Restart recovery marks unfinished jobs interrupted and releases stale leases.
Delivery is at-least-once, with bounded retry attempts and stable message IDs.
See [operations.md](operations.md) for timing/deduplication and retention limits.

The frontend adds sign-in, Monitoring, Alert inbox, and Team & access. Auth/CSRF
state is kept in memory; the opaque cookie is HttpOnly. Visible dashboard views
periodically refresh snapshots/operational data. Role changes/password resets
revoke server sessions and the next private request returns the user to sign-in.

## Deployment and limits

A multi-stage Docker build produces frontend assets and a non-root Python
runtime. Compose binds loopback, supplies a private persistent data volume,
read-only root filesystem, temporary scratch space, and a single server worker.
SMTP and API docs are off in the container defaults. Health/readiness are public
operational signals, while evidence APIs require authentication.
See [deployment.md](deployment.md) for setup and pending container verification.

The service remains one local shared workspace. It has no distributed queue,
tenant isolation, automatic retention/remediation, or hosted deployment. Scans
and collectors are synchronous and bounded. Supported scopes do not cover all
policy semantics. The synthetic model remains an experimental baseline;
real-world evaluation is outside this phase.
