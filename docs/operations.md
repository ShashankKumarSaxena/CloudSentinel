# Operations

## Jobs, schedules, and ownership

An analyst submits an approved account collection in Cloud connections. The API
requires an Idempotency-Key, returns 202, and persists the job before collection.
Retries with the same user/key/payload return the same job; reusing the key for
another payload returns 409. The queue defaults to 500 pending/running jobs.
Only pending jobs can be cancelled. Account approval is checked again when a job
executes, so disabling a registry entry stops queued work from using it.

The worker checks work every two seconds, processing bounded collections serially.
The production worker holds a dedicated PostgreSQL advisory lock and a persisted
fencing identity. A replacement worker invalidates old claims before snapshots
or schedule completion can publish. A stale or failed worker exits for Docker
restart. Interrupted jobs retry up to three claimed attempts, then fail. Work is
at least once: a scan committed immediately before a crash may be repeated in
history. Review failures and provider request budgets rather than assuming an
exactly-once cloud read.

Administrators create schedules with 60-second to seven-day intervals. New
enabled schedules first run after their interval. In production, Run now moves
an **enabled** schedule due immediately for the worker; it does not collect in
the API. Enable paused schedules before running them. Demo mode retains immediate
manual runs, including paused schedules. Editing a running schedule returns 409.
Failures back off from 60 seconds up to one hour; busy scans defer ten seconds.
Missed intervals coalesce to one run. Interrupted scheduled runs recover after
restart. There is no execution while the worker is stopped and no distributed
scheduler or supported multiple-worker scaling.

## Alert review and recurrence

Snapshots, alert observations, account pointers, and scan audits commit together.
The inbox includes findings, incomplete coverage, and collection/schedule failures.
Repeat observations of an active finding do not flood the inbox. An explicit
passing configuration check ends that alert episode; a later failure opens a new
one. Resolving a configuration finding that still fails on the next scan reopens
its disposition and alerts for review. Missing/unknown checks never count as a
pass. Reviewing an ML finding does not re-alert the identical historical window.
Acknowledgment, finding disposition, and verified cloud remediation are separate.

Alerts have bounded pagination; filters apply to the loaded page. Jobs expose
pagination too. The interface polls rather than using websockets. Run/audit views
show recent records; older records remain stored until explicit maintenance.

SMTP is opt-in. New alerts at/above the configured severity enter a durable
outbox. Failed attempts retry at 60/120/240/480 seconds and stop after five
attempts. Administrators can retry failed delivery. Messages use a stable
Message-ID and minimal source/alert summary. Delivery is **at least once**: an SMTP
acceptance followed by a crash can create a duplicate message. Existing
inbox-only alerts are not automatically queued after SMTP is enabled.

## Health and diagnostics

| Endpoint/tool | Meaning |
| --- | --- |
| `/api/v1/health` | Public process liveness; no cloud connectivity assertion |
| `/api/v1/ready` | Database, administrator setup, valid registry, and fresh production worker heartbeat; returns 503 when unavailable |
| `/api/v1/operations` | Authenticated worker, schedule, email, unread-alert status |
| `python scripts/preflight.py` | Configuration/dependency check without database, cloud, IdP, or SMTP access |
| `python scripts/smoke_test.py --url https://YOUR_DOMAIN --authenticated` | Running server checks; prompts for local credentials |

Production logs are JSON with request IDs, route templates, status, and duration.
The same request ID is returned as a response header. Monitor worker health,
queue age, failures, unavailable coverage, PostgreSQL capacity, free disk,
certificate expiry, backups, and mail failures through your existing operations
platform. No hosted metrics exporter, on-call routing, or external immutable
audit integration is bundled.

Use `scripts/manage_users.py reset-password --username owner` through the running
API container for local password recovery. The command prompts securely and
revokes sessions; it does not re-enable disabled users. The CLI reads the same
deployment settings/secret files as the application.

## PostgreSQL backup and fresh-project restore

From the root, with the production deployment running:

```bash
python3 scripts/production_backup.py backup backups/workspace-2026-10-15.tar.gz
```

The helper uses `deploy/production/.env`, a custom-format `pg_dump`, model copies,
and a checksummed private archive. Use new filenames. Stop retraining during
backup for consistent database/model pairing. Backups contain evidence and
password hashes, are **not encrypted**, and must be encrypted/protected off-host.
Checksums do not authenticate an archive. Only restore trusted local backups.
Back up deployment configuration and private CA/secrets separately.

Restore into a **fresh Compose project** with an empty database/model volume;
keep the original project for rollback. Start only the new database first:

```bash
docker compose --env-file deploy/production/.env -f deploy/production/compose.yaml -p cloudsentinel-recovery up -d database
# Wait for its health check before restoring:
python3 scripts/production_backup.py restore backups/workspace-2026-10-15.tar.gz --project cloudsentinel-recovery
```

The restore helper requires stopped API/worker and an empty database. It validates
archive paths/checksums/bounds before database restore, uses one PostgreSQL restore
transaction, copies trusted models, revokes sessions, pauses schedules, cancels
unfinished jobs, and suppresses queued email. It does not start the app. Review
scope and restored evidence before starting services and re-enabling automation.
If restore fails after database commit/model copy, retry into another fresh
project; it will not overwrite partial state. The helper uses the base Compose
file only; apply any identity/SSO/email overlays when starting the recovered app.
Do not run two recovery proxies on the same 80/443 ports.

## SQLite demo backup

```bash
.venv/bin/python scripts/backup.py backup backups/demo.tar.gz
# Stop the demo, then restore into a fresh directory:
.venv/bin/python scripts/backup.py restore backups/demo.tar.gz --database .runtime-restored/cloudsentinel.db
CLOUDSENTINEL_DB="$PWD/.runtime-restored/cloudsentinel.db" bash scripts/demo.sh
```

SQLite online backup preserves the live source and excludes sessions from the
copy. Restore validates checksums and database integrity, pauses automation,
clears worker heartbeat, and cancels unfinished jobs. Model artifacts must be in
the sibling `models/` directory for inclusion. Never remove active WAL/SHM files.

## Retention and upgrades

Retention is explicit, defaults to dry run, and preserves at least 30 days:

```bash
# Use inside the production API container, with its deployment configuration:
python scripts/retention.py --days 90
python scripts/retention.py --days 90 --apply
```

It removes eligible old scans, terminal jobs/runs, and acknowledged terminal
alerts; preserves latest/current account snapshots, unfinished work, and the
audit log; and records applied maintenance. Audit and triage history still grow:
plan archive/storage capacity under your organization's retention policy.
Backup before upgrades or applying maintenance. Migrations are transactional and
versioned, with no automatic downgrade. Restore a pre-upgrade backup into a fresh
project for rollback. Older scan evidence stays immutable; new configuration
fingerprints include account identity, so legacy triage IDs are not transferred
to newly generated finding IDs.
