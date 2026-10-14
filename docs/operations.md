# Operating the workspace

## Monitoring and run history

An administrator creates a schedule in Monitoring. Select a synthetic fixture or
an explicit live provider/region/account scope. Intervals range from 60 seconds
to seven days; the form offers common choices. New enabled schedules first run
after their interval. **Run now** also works for paused schedules and does not
enable them. Enable/pause and interval edits reset the next run time.
There are no preconfigured schedules and no implicit live collection.

The background worker checks due work every two seconds. Each claim creates a
saved run and a five-minute lease in one SQLite transaction. Only one process
can own the database's monitoring lock; use one server worker and one replica.
Manual scans, live collections, and model training share a mutation lock with
scheduled scans. A busy operation defers the scheduled run for ten seconds
without counting it as a failure. Editing a running schedule returns 409.

Successful runs save a scan ID and schedule the next run relative to completion.
Failures preserve prior scans, record a safe error, and retry with increasing
backoff (60 seconds up to one hour). Missed intervals coalesce to one due run,
rather than replaying every missed execution. Work is local and synchronous;
there is no distributed task queue or execution while the service is stopped.

On restart, the owner of the process lock marks running records interrupted,
releases stale leases, and makes enabled interrupted work due again after ten
seconds. A scan already committed before a crash remains in history even if its
run record could not be finalized. Finding deduplication prevents another inbox
entry for the same fingerprint. Recent run lists show the latest 100 records;
older records remain in SQLite.

## Alert lifecycle

A completed scan and its alert/audit inserts commit in one transaction. Failure
to save the associated operations data also rolls back the scan. Alerts cover:

- Configuration and ML findings, including method/provider/account evidence.
- Partial collection coverage, with unavailable scopes.
- Scheduled-run failures, deduplicated within each failure episode.

Finding alerts are keyed by source, provider, account, and stable finding ID.
Repeated snapshots do not flood the inbox. Deduplication is permanent for the
fingerprint in this release: a recurring identical finding does not re-open an
acknowledged alert or create a new alert episode. Resolved team dispositions are
not re-alerted. Coverage alerts deduplicate equivalent failed scope sets; a
schedule failure can create a new episode after a successful run.

Alert inbox displays pages of 200; search/review filtering applies to the current
page. It reports total and unreviewed counts, source, severity, delivery status,
and evidence. Analysts/administrators can acknowledge alerts. Acknowledgment is
independent of finding triage and does not verify cloud remediation or cancel an
email already queued. All roles can inspect the shared inbox.

The inbox is refreshed every 30 seconds while visible; monitoring status/run
lists refresh every 15 seconds. The main snapshot/history counters refresh every
30 seconds. Refresh buttons are available. There is no websocket stream.

## Optional email

Default operation is **inbox only**. To deliver externally, explicitly configure
`CLOUDSENTINEL_SMTP_ENABLED=1`, host, sender, and comma-separated recipients.
Use `starttls` (typically port 587) or `ssl` (typically 465), with verified TLS.
A username may be configured; its password is read from
`CLOUDSENTINEL_SMTP_PASSWORD_FILE` at delivery time. Credentials never enter the
UI. See `.env.example` and [deployment.md](deployment.md) for settings/mounts.

New alerts at or above `CLOUDSENTINEL_ALERT_MIN_SEVERITY` (default `high`) enter
the durable outbox. Synthetic alerts are eligible too; review recipients before
enabling. Medium ML findings require a `medium` threshold. Existing inbox-only
alerts are not automatically queued after enabling SMTP.

A pending delivery is claimed with a lease and saved attempt count. Failed
attempts retry after 60, 120, 240, and 480 seconds, with a terminal failure after
five attempts. Administrators can retry a failed delivery from its alert drawer
once server SMTP is configured. Pending deliveries survive restart; delivery
stops while SMTP or the worker is disabled. Recovery restores interrupted
attempts without exceeding the limit.

Messages include source, alert ID, a severity subject, and a minimal summary.
Detailed cloud evidence stays in the workspace. A stable Message-ID accompanies
retries. SMTP delivery is **at-least-once**: a crash after server acceptance and
before saving success can produce a duplicate. The inbox fingerprint prevents
repeated scan alerts, not duplicate acceptance by an external mail server.
No real SMTP messages were sent during implementation; transport tests are mocked.

## Access and audit

Create the first administrator with `make create-admin` on the host, or the
container command in [deployment.md](deployment.md). Administrators create other
accounts and inspect the latest 200 audit records in Team & access.
Audit records cover logins, user/password changes, scans/model training, schedule
outcomes, triage, alert acknowledgment/delivery, and report exports. They are
operational records, not an immutable external audit ledger; someone with local
database access can modify them.

Password changes, role changes, and disabling access revoke account sessions.
To recover a forgotten password as the local operator:

```bash
.venv/bin/python scripts/manage_users.py reset-password --username owner
```

Use the same `CLOUDSENTINEL_DB` value as the running service. Resetting a password
does not re-enable a disabled user. Another administrator manages enabled status.
Local operator scripts can access the data directory directly; browser roles do
not protect against someone who controls the host.

## Backup and restore

Use a private destination and distinct archive names:

```bash
.venv/bin/python scripts/backup.py backup backups/cloudsentinel-2026-10-15.tar.gz
```

The script uses SQLite's online backup API, removes sessions only in the copy,
consolidates WAL data, includes completed sibling model artifacts/active pointer,
and writes a checksum manifest in a mode-600 gzip archive. Active users keep
their sessions. Model versions are immutable, but avoid retraining during a
backup if you need an exact database/model-point-in-time pair.
The archive includes password hashes and account evidence. It is **not encrypted**.
Protect or externally encrypt it. Checksums detect corruption, not authenticity.
Only restore trusted locally generated archives.

Stop the service before offline restore. Choose a fresh data directory:

```bash
.venv/bin/python scripts/backup.py restore backups/cloudsentinel-2026-10-15.tar.gz \
  --database .runtime-restored/cloudsentinel.db
CLOUDSENTINEL_DB="$PWD/.runtime-restored/cloudsentinel.db" bash scripts/demo.sh
```

Restore rejects existing databases/model directories, unsafe paths, links,
duplicate archive entries, archives above 1 GB, bad checksums, and failed SQLite
integrity checks. Users, scans, triage, completed models, alerts, and audit records
are retained; sessions are removed, schedules paused, and pending/sending emails
converted to inbox-only. Sign in and review scope before enabling schedules.

Backups by default use `.runtime/cloudsentinel.db`, or `CLOUDSENTINEL_DB` if set.
The `--database` option selects a specific database. Server model artifacts must
be in the sibling `models/` directory for inclusion. See
[deployment.md](deployment.md) for Docker-volume backup/recovery.

## Health and storage

`GET /api/v1/health` is public liveness plus model readiness metadata.
`GET /api/v1/ready` returns 200 only when the database/model/account setup is
ready and an enabled worker is alive; otherwise 503. `/api/v1/operations` is
signed-in operational status, including worker error/heartbeat and unread count.
No public endpoint returns cloud evidence, credentials, or account lists.

State and completed model versions grow over time; there is no automatic
retention cleanup. Review disk usage, run frequency, backup size, and host storage.
Do not delete SQLite WAL/SHM files while the service is running. Keep the same
single-process ownership model when copying/migrating a workspace.
