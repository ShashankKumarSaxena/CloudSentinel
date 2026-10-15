# Validation and rollout evidence

This record describes local checks for the unreleased 1.0.0 deployment foundation.
It separates code/package verification from a completed production rollout.
The operator selected finishing the package and installing/running new production
services later. No cloud accounts, real SMTP messages, or hosted deployment were
used during implementation.

## Completed locally

| Check | Result |
| --- | --- |
| Backend test discovery | **133 tests: 129 passed, 4 skipped** |
| Detection and provider mappings | Synthetic inventories/activity; real boto3 Stubber and mocked Azure/GCP REST responses |
| API and access | In-process ASGI routing/lifespan, required sign-in, roles, cookie flags, CSRF/origin, expiry/revocation, safe errors |
| Production policy | SQLite-backed API fixture exercises production settings, empty startup, no demo/train, queued approved jobs, worker readiness; this is not a PostgreSQL execution test |
| Account boundaries | Approval/region checks, execution-time disablement, separate snapshot pointers, account-aware finding IDs, stale triage rejection |
| Durable operations | Idempotency, queue bounds/cancellation, concurrent claims, restart recovery, fencing obsolete workers, scan/alert/triage audit rollback, finding recurrence |
| Recovery and maintenance | Private/checksummed archives, unsafe path/tampering rejection, session revocation, paused automation, unfinished job cancellation, retention preserving current evidence/unfinished work/audit |
| Secret preparation | Offline OpenSSL CA/server generation, hostname verification, private paths, no-overwrite and invalid-domain checks |
| Python formatting | Black 24.10.0 across backend/scripts |
| Frontend | TypeScript checking and Vite production build, version 1.0.0 |
| Frontend formatting | Available Prettier 2.5.1 check passed; pinned 3.6.2 check awaits installation |
| Compose | Demo and production configuration; OIDC, SMTP, AWS/Azure/GCP identity overlay merges |
| Package checks | Shell syntax, Python compilation, local documentation links, and Git whitespace checks |
| Configuration preflight | Offline demo dependency/configuration check; no external connectivity asserted |

The demo remains 18 resources, 30 configuration checks (14 pass/16 fail), 330
activity events, six hourly windows, and 19 findings. Posture is 47% of evaluated
configuration checks. Synthetic Isolation Forest holdout metrics remain 78.95%
precision, 25.00% recall, and 2.22% false-positive rate. The fixed comparator has
higher recall. No real-world ML improvement is claimed.

## Deferred checks and their limits

- **Two PostgreSQL integration tests skipped:** no configured test database or
  installed psycopg runtime. The adapter, pooling, TLS connection, PostgreSQL
  migrations, locking, and production restore need execution against PostgreSQL.
- **Two OIDC protocol tests skipped:** Authlib/HTTPX dependencies are not installed.
  The tests use signed mock identity tokens/PKCE and are included for later
  verification. A real IdP discovery/sign-in/offboarding test is also required.
- **Production identity SDKs not installed:** Azure identity and Google auth
  factories require installation and live expiry/refresh/permission checks.
  Mocked provider mapping tests cannot establish workload identity correctness.
- **No Docker image build or container startup:** Compose configuration passed;
  non-root application startup, volumes, networking, HTTPS, database TLS, and
  container backup/restore remain runtime checks.
- **No browser visual/click-through verification or live-port smoke run:** browser
  tools are unavailable and local socket connections were restricted. Type/build
  success does not establish responsive layout or interactive accessibility.
- **No live provider or SMTP validation:** actual API permissions, API versions,
  coverage, request budgets, sender acceptance, and delivery limits remain unknown.
- **Dependency installation/formatter release check deferred:** PyPI/npm could not
  be reached. The new pinned Prettier lock entry omits a registry integrity hash;
  refresh/review it after connectivity returns. All pre-existing integrity hashes
  are preserved. Run `make format` and `make check` with installed developer tools.
- **Hosted CI, image/vulnerability scans, capacity tests, and external security
  review have not executed here.** Workflows and Dependabot configuration are
  provided. These are not evidence of certification or a production SLA.

Changes remain local and uncommitted. No GitHub push or infrastructure mutation
was performed.

## Run the remaining checks

```bash
bash scripts/setup.sh --dev
npm --prefix frontend install --package-lock-only
make format
make check
make docker-config
# Set CLOUDSENTINEL_TEST_DATABASE_URL to a disposable PostgreSQL database:
.venv/bin/python -m unittest backend.tests.test_postgresql_integration -v
.venv/bin/python -m unittest backend.tests.test_oidc_integration -v
```

Then follow [deployment](deployment.md) in a controlled environment and record
results for the following gates before accepting production traffic:

1. Verify image builds, database TLS/hostname validation, HTTPS, secure cookies,
   allowed hosts/proxy headers, volume permissions, and readiness after bootstrap.
2. Test local admin recovery, viewer/analyst/admin actions, session revocation, and
   corporate sign-in with approved/unapproved/disabled subjects and required MFA.
3. Collect one small approved account per provider. Inspect raw source against
   normalized evidence, unknown/partial coverage, scope enforcement, token refresh,
   and least-privilege permissions. Test denied and expired credentials.
4. Create a paused schedule, enable/request a run, restart/kill the worker during
   work, and confirm recovery/fencing and prior valid account evidence. Monitor
   queue age and scan duration under representative expected load.
5. Test new/recurring findings, acknowledgments, configuration pass/fail episodes,
   and optional mail failures/retries with a reviewed test mailbox.
6. Back up and restore into a fresh project, confirm revoked sessions/paused
   automation, compare evidence, and measure recovery time. Check retention dry
   run before applying it and verify off-host backup protection.
7. Review wide/narrow layouts, keyboard focus, sign-in, account switching, job
   inspection, filtering, triage, history, and report export in supported browsers.
8. Review dependencies/images, network exposure, credential/CA rotation, logging,
   monitoring, capacity, and security issues under your organization's process.

The [architecture](architecture.md) defines the single-organization/single-worker
support envelope and bounded collector scope. Expand it only with corresponding
integration, load, and recovery evidence.
