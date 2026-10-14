# Local Docker deployment

The Phase 3 package is intended for one service on your own machine. Docker
Desktop must be running. Docker image build/container execution was deferred by
the user; only Compose configuration was verified in this session.

## Startup

Run from the project root:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=60 cloudsentinel
```

First startup fits the bundled synthetic model and saves a synthetic snapshot.
Wait for the service to become healthy, then create the first administrator:

```bash
docker compose exec cloudsentinel python scripts/manage_users.py create-admin
```

Choose your own username and a 12–256 character password. The password is entered
interactively; it is not a command-line argument. Open
**http://127.0.0.1:8000** and sign in. If no account exists, the application shows
setup instructions and readiness returns 503. This is expected until bootstrap.
The in-app `make create-admin` hint applies to a host installation; containers
must use the Compose command above to update the container's database.

To use a different port because the host demo already occupies 8000:

```bash
CLOUDSENTINEL_PORT=8001 docker compose up -d --build
# Dashboard: http://127.0.0.1:8001
```

The dashboard and API share one origin. Use the same hostname consistently when
signing in: cookies for `localhost` and `127.0.0.1` are separate.

## Verification after startup

From a host with Python available:

```bash
python3 scripts/smoke_test.py
python3 scripts/smoke_test.py --authenticated
# Custom port:
python3 scripts/smoke_test.py --base http://127.0.0.1:8001 --authenticated
```

Public checks verify liveness/model readiness, required authentication, rejection
of anonymous private access, and dashboard HTML. After bootstrap they also verify
readiness. Authenticated checks prompt for credentials, inspect private routes,
and revoke their session when finished. They do not scan a real account or send
notifications. Report export records an audit event.

Use Monitoring to create a **synthetic**, paused schedule and select **Run now**.
Check that the run succeeds, a new snapshot appears, and the existing demo finding
alerts are not duplicated. Enable it only if periodic execution is desired.
Inspect Alert inbox and Team & access. See [validation.md](validation.md) for the
manual browser checklist.

## Container defaults and persistence

- Multi-stage Node 24 frontend build, Python 3.12 runtime, pinned application dependencies.
- Non-root UID/GID 10001; one Uvicorn worker per database.
- Loopback-only port; explicit local allowed hosts; no anonymous private API.
- Read-only container root filesystem; a 64 MB temporary filesystem at `/tmp`.
- All Linux capabilities dropped; no-new-privileges; process and memory limits.
- SQLite and model artifacts in `/var/lib/cloudsentinel`, on the named data volume.
- SMTP disabled; API docs disabled; monitoring worker enabled with no schedules by default.
- Liveness health probe and 150-second shutdown grace for bounded collection work.

`docker compose down` stops the service and retains the named volume. Starting it
again preserves users, scans, triage, schedules, alerts, and models. Avoid the
volume-removal option unless you explicitly intend to erase that data. Host
`.runtime/` and the Docker named volume are independent workspaces.

The health probe checks liveness. `/api/v1/ready` checks the database, model,
initial account setup, and enabled worker. A healthy container can still need
administrator bootstrap. Monitoring does not run while the service is stopped;
on restart, interrupted work is recorded and overdue enabled schedules run once.

Dockerfile and Compose behavior follow the official
[Compose service reference](https://docs.docker.com/reference/compose-file/services/)
and [health-check startup guidance](https://docs.docker.com/compose/how-tos/startup-order/).
Base image tags are not immutable digests; dependencies are pinned, but image
rebuilds can include newer OS/runtime updates.

## Optional cloud and SMTP configuration

For the synthetic workflow, skip this section. Live access and real notification
delivery were not performed during implementation.

The default image contains boto3 and HTTPS REST collectors. Azure/gcloud CLIs
are not installed. Use explicitly configured local token files for Azure/GCP,
or use the host installation with its signed-in provider CLIs. Token files are
bounded, validated, and read at collection time. They are not auto-refreshed.
Expired credentials produce a failed or partial run with safe diagnostic text.

Create an ignored `compose.local.yaml` with only the mounts/configuration you
intend to use. For example, an Azure token mount:

```yaml
services:
  cloudsentinel:
    environment:
      AZURE_SUBSCRIPTION_ID: your-subscription-id
      CLOUDSENTINEL_AZURE_TOKEN_FILE: /run/secrets/azure_token
    volumes:
      - ./secrets/azure_token:/run/secrets/azure_token:ro
```

Obtain the token on the host through your signed-in Azure CLI, with the Resource
Manager audience, and write it directly to the file. Keep `secrets/` private
(mode 700) and mount only that file. The mounted file must be readable by UID
10001; Docker bind mounts retain platform-dependent permissions. One local
option is a read-only mode 444 token file inside the private host directory.
Verify readability without printing its contents before configuring a schedule.
Refresh the file locally before token expiry. For GCP use a gcloud access token
file with `CLOUDSENTINEL_GCP_TOKEN_FILE` and `GOOGLE_CLOUD_PROJECT`.

AWS uses its normal boto3 chain. Mount only the chosen read-only credential/config
files at explicitly configured locations, including the required SSO token cache
if that profile needs it. Mounting host credentials is an explicit operator step;
the supplied Compose file mounts no host credentials.

SMTP override example (review recipients before enabling):

```yaml
services:
  cloudsentinel:
    environment:
      CLOUDSENTINEL_SMTP_ENABLED: "1"
      CLOUDSENTINEL_SMTP_HOST: smtp.example.org
      CLOUDSENTINEL_SMTP_PORT: "587"
      CLOUDSENTINEL_SMTP_TLS: starttls
      CLOUDSENTINEL_SMTP_FROM: cloudsentinel@example.org
      CLOUDSENTINEL_SMTP_TO: security@example.org
      CLOUDSENTINEL_SMTP_USER: cloudsentinel@example.org
      CLOUDSENTINEL_SMTP_PASSWORD_FILE: /run/secrets/smtp_password
      CLOUDSENTINEL_ALERT_MIN_SEVERITY: high
    volumes:
      - ./secrets/smtp_password:/run/secrets/smtp_password:ro
```

Keep the password out of YAML and environment values. Apply the same private
host-directory/readable-file treatment. All new matching alerts, including
synthetic alerts, can be emailed once enabled. Existing inbox-only alerts are
not retroactively queued. Only encrypted `starttls` or `ssl` transport is
supported. See [operations.md](operations.md) for retry/deduplication semantics.

Apply the selected override explicitly:

```bash
docker compose -f compose.yaml -f compose.local.yaml config --quiet
docker compose -f compose.yaml -f compose.local.yaml up -d --build
```

Use those same `-f` flags for subsequent Compose commands when you use overrides.
The host scripts do not load `.env`; Compose reads it for interpolation and passes
only settings listed in the service configuration. `.env.example` documents the
supported application settings.

## Recovery, backups, and upgrades

Recover an existing account locally without exposing a password in arguments:

```bash
docker compose exec cloudsentinel python scripts/manage_users.py reset-password --username owner
```

A reset revokes that account's sessions. Additional accounts are created in
Team & access after sign-in; the bootstrap command cannot create a second owner.

Create a backup in the persistent writable directory and copy it out:

```bash
docker compose exec cloudsentinel python scripts/backup.py backup /var/lib/cloudsentinel/backup.tar.gz
mkdir -p backups
chmod 700 backups
docker compose cp cloudsentinel:/var/lib/cloudsentinel/backup.tar.gz backups/cloudsentinel.tar.gz
chmod 600 backups/cloudsentinel.tar.gz
```

Use distinct archive names for successive backups. The archive contains the
SQLite snapshot and model files but excludes sessions. It is private, not
encrypted. Only restore your own trusted archives; checksums detect corruption,
not a malicious replacement. An offline host restore can verify/recover into a
fresh directory:

```bash
.venv/bin/python scripts/backup.py restore backups/cloudsentinel.tar.gz \
  --database .runtime-restored/cloudsentinel.db
CLOUDSENTINEL_DB="$PWD/.runtime-restored/cloudsentinel.db" bash scripts/demo.sh
```

This requires host dependencies from `scripts/setup.sh`. For a Docker restore,
stop the service and point a reviewed `compose.local.yaml` override at a fresh
named volume. Keep the original volume for rollback:

```yaml
services:
  cloudsentinel:
    volumes:
      - cloudsentinel-restored-data:/var/lib/cloudsentinel
volumes:
  cloudsentinel-restored-data:
```

The mount with the same container target replaces the original data mount.
After saving that override, restore offline with a temporary root helper so it
can read the private host archive and assign restored files to the application
UID. The application itself continues to run as UID 10001:

```bash
docker compose down
docker compose -f compose.yaml -f compose.local.yaml run --rm --no-deps \
  --user 0 -v "$PWD/backups:/restore:ro" cloudsentinel sh -c \
  'python scripts/backup.py restore /restore/cloudsentinel.tar.gz --database /var/lib/cloudsentinel/cloudsentinel.db && chown -R 10001:10001 /var/lib/cloudsentinel'
docker compose -f compose.yaml -f compose.local.yaml up -d
```

Use a fresh volume name if that recovery volume already contains a workspace.
Existing databases and model directories cannot be overwritten by restore.
Sign in again, verify the restored evidence, and review paused schedules before
enabling them. See [operations.md](operations.md). These container recovery
commands are packaged instructions; Docker execution remains unverified.

Before an upgrade, back up the current workspace, then build/start the new image.
Phase 3 creates new tables without rewriting legacy scan evidence. Downgrading
across a schema change is not a supported automated workflow.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Cannot connect to Docker | Start Docker Desktop; then rerun Compose |
| Port already in use | Stop the host demo or select `CLOUDSENTINEL_PORT=8001` |
| First request takes time | Wait for synthetic model initialization; inspect logs |
| Readiness is 503 with setup required | Bootstrap the first administrator in the container |
| Login fails after an upgrade | Phase 3 has no default credentials; create or recover the account in the correct workspace |
| Schedule cannot be edited | A run holds its lease; wait for completion and refresh |
| Second server refuses startup | Stop it; use one process per database |
| Mounted credential fails | Review file readability, audience, expiry, read permissions, and scope |
| Email stays inbox-only | SMTP is disabled or severity falls below the configured threshold |

The supplied deployment is loopback HTTP, so secure-cookie mode is off.
Public hosting is outside this release. A separately reviewed HTTPS deployment
would need explicit host/origin/proxy settings and secure cookies; switching
secure cookies on while using plain HTTP prevents normal browser sign-in.
