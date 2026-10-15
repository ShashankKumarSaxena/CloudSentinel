# Deployment

The root `compose.yaml` is an isolated loopback demo. Real accounts use
`deploy/production/compose.yaml`: PostgreSQL 17 with TLS, one worker, one API,
and Caddy HTTPS. These are packaged deployment instructions; Docker execution,
provider identity, and PostgreSQL runtime remain to be verified on your host.

## Offline demo

```bash
bash scripts/setup.sh
make create-admin
make demo
```

Or use `docker compose up -d --build`, followed by
`docker compose exec cloudsentinel python scripts/manage_users.py create-admin`.
Open http://127.0.0.1:8000. To select another demo port, run
`CLOUDSENTINEL_PORT=8001 docker compose up -d --build`.
The named `cloudsentinel-data` volume retains SQLite and the synthetic model.

## Production prerequisites

Use a maintained Linux host with Docker Engine and Compose v2, sufficient disk
for PostgreSQL/evidence/backups, and at least 4 GB available application memory
(the API and worker each have a 2 GB limit, plus database/proxy overhead).
Choose an organization-controlled DNS name pointing to the host. Caddy needs
inbound 80/443 and certificate-authority connectivity for its default automatic
HTTPS flow. Put access controls appropriate to your organization at the boundary.
Use a reviewed internal-certificate Caddy configuration for private-only DNS.

Do not expose PostgreSQL or API port 8000. Keep one API process and one worker
replica. Review subnet `172.30.80.0/24` for conflicts; update the subnet and trusted
proxy IP together if needed. Persist and back up the volumes. Image tags are
pinned by release family; resolve and record reviewed image digests in your
release process, and scan/update images before rollout.

## 1. Prepare configuration and private files

Run from the project root. Python/OpenSSL are needed for local preparation;
production Python/Node dependencies are installed by the Docker build.

```bash
cp deploy/production/.env.example deploy/production/.env
cp config/accounts.example.json config/accounts.local.json
python3 scripts/configure_production.py --domain security.your-company.com
```

Edit `deploy/production/.env` to set your real `CLOUDSENTINEL_DOMAIN`. The prepare
command validates the domain and creates a fresh `secrets/production/` directory;
it does not edit the environment file or your accounts. It refuses to overwrite
existing secrets. It creates independent application/admin database passwords,
a verify-full database URL, private CA and server certificate, and OIDC state key.
It neither contacts clouds nor creates users.

The host secret directory is mode 700. Files mounted through Compose are mode
444 inside that private directory so UID 10001 and PostgreSQL can read them;
the CA private key remains mode 600 and is never mounted. Keep the directory
private. On a shared host, use an appropriate secret manager instead of widening
its permissions. Never commit generated files or print secret values into logs.

Edit `config/accounts.local.json`. Start with disabled accounts. Use the
[provider guide](cloud-collectors.md), permission templates, and an approved
workload identity. Azure/GCP currently collect subscription/project-wide and
require `regions: ["global"]`; AWS requires explicit regional scopes. The registry
is mounted read-only into API and worker. No cloud access is performed until a
user requests a collection or enables a live schedule.

## 2. Configure workload identity

Only the worker gets provider identity mounts. The base production image includes
provider SDKs, not Azure/gcloud CLIs. Choose a supplied overlay as a starting point:

| Overlay in `deploy/production/` | Operator responsibility |
| --- | --- |
| `aws-web-identity.example.yaml` | Configure the base identity's role trust and rotated web-identity token; target cross-account role/external ID goes in registry |
| `azure-workload-identity.example.yaml` | Configure tenant/client federated trust and a rotated token matching its audience |
| `gcp-workload-identity.example.yaml` | Supply an external-account federation configuration and rotated subject token; optional target service account in registry |

Copy the selected example to an ignored local overlay, replace placeholders,
and include it on **every** Compose invocation. Mount a directory rather than a
single rotating file when an identity agent replaces token files atomically.
Compose does not issue or rotate federation tokens. Managed identities also
require the host/platform identity endpoint to be reachable by the worker.
Configure provider policies yourself; the application does not create cloud IAM.

The examples show authentication wiring, not a universal trust policy. Confirm
issuer, subject, audience, account scope, role permissions, and expiry with your
cloud administrator before enabling an account.

## 3. Validate and start

Base commands below omit optional overlays. Add `-f deploy/production/your.local.yaml`
after the production file when using them. Never paste live secrets into command
arguments.

```bash
docker compose --env-file deploy/production/.env -f deploy/production/compose.yaml config --quiet
docker compose --env-file deploy/production/.env -f deploy/production/compose.yaml up -d --build
# Bootstrap after worker/API are healthy. CLI prompts for the password:
docker compose --env-file deploy/production/.env -f deploy/production/compose.yaml exec api python scripts/manage_users.py create-admin
```

The worker connects/migrates first; the API follows its health check. The API
health check is liveness, so initial administrator setup can be completed while
readiness is 503. Visit `https://security.your-company.com`, sign in, and inspect
`/api/v1/ready`. Production has an empty workspace and no synthetic model. Readiness
does not test cloud permissions; request one small approved account manually,
inspect its coverage and evidence, then create schedules only after review.

The proxy trusts forwarded headers from one configured internal proxy address.
Do not set `FORWARDED_ALLOW_IPS=*`. The API has internal networking only; worker
cloud/SMTP egress and proxy public egress use separate networks.

## 4. Optional corporate sign-in and email

For OIDC, copy `oidc.example.yaml` to an ignored local overlay. Set the HTTPS
issuer and client ID. Register exactly
`https://YOUR_DOMAIN/api/v1/auth/oidc/callback` as the redirect URI. Place the IdP
client secret in `secrets/production/oidc_client_secret` (readable file under the
private directory). The generated `oidc_state` is a separate random signing key.
The overlay gives the API identity-provider egress; it does not mount cloud keys.

Create each SSO user in Team & access with its exact immutable IdP subject and
local role. Existing users can be linked through the administrator-only
`POST /api/v1/users/{user_id}/identity` with `{"subject":"..."}` and session CSRF.
Linking disables password sign-in for that user. Retain the local recovery admin.
No email matching or just-in-time provisioning is enabled. Enforce MFA/conditional
access at the IdP. Disabling a user in CloudSentinel revokes local sessions;
IdP offboarding alone does not instantly revoke an existing local session.

For email, copy `smtp.example.yaml`, set reviewed addresses/host/TLS settings,
and place its password in the private secret directory. Both API and worker need
the same enablement/severity configuration so new alerts enter the outbox; only
the worker needs the SMTP password. Existing inbox-only alerts stay inbox-only.
Review delivery behavior in [operations](operations.md) before sending messages.

## Recovery and maintenance

See [operations](operations.md) for backup, fresh-project restore, retention,
password recovery, monitoring, and upgrades. Never use `docker compose down -v`
against a workspace you need to preserve. Backups and local CA/private secrets
need their own secure off-host retention plan.

The generated database certificate expires after one year; monitor it and renew
before expiry with the same private CA (or a planned CA replacement). Keep the
`database` SAN and restart database/API/worker after replacing mounted files.
Rotate database passwords in PostgreSQL and the matching secret files together;
recreating a secret file alone does not change an initialized database role.
OIDC state-key rotation invalidates in-flight sign-ins. Recreate containers after
changing file-backed secrets so bind mounts do not retain an old inode.

For upgrades, back up first, stop API/worker, build the reviewed image, then start
worker/API so transactional migrations run before traffic. There are no automatic
down migrations; rollback uses the previous image and a pre-upgrade backup in a
fresh project. Review [validation](validation.md) before accepting production use.
