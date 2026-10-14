# Phase 3 validation evidence

Phase 3 passes the backend suite, TypeScript checks, production frontend build,
and Docker Compose configuration validation. Detection uses synthetic data and
mocked cloud APIs. Notification delivery uses mocked SMTP. The user selected
finishing the deployment package and running Docker later.

## Verified results

| Check | Result | Evidence |
| --- | --- | --- |
| Backend/API/model/provider/security/operations suite | Passed | **94 tests** using temporary SQLite databases, local models, real ASGI routing/middleware, AWS SDK Stubber, mocked REST and SMTP |
| TypeScript | Passed | `npm --prefix frontend run check` |
| Production frontend | Passed | `npm --prefix frontend run build`, v0.3.0 |
| Compose configuration | Passed | `docker compose config --quiet` |
| Synthetic combined scan | Passed | 18 resources; 30 checks; 330 events; six windows; 16 rule and three ML findings |
| Authentication/roles | Passed | Anonymous private access blocked; viewer read-only; analyst scan/triage; administrator management; local-only bootstrap |
| Session protections | Passed | Salted hashes, hashed tokens, idle/absolute expiry, throttling, bounded sessions, CSRF, cookie flags, logout/revocation |
| Scheduling | Passed | Concurrent claim race, persisted runs, pause/manual run, busy deferral, backoff, exclusive process lock, shutdown release, interrupted recovery |
| Alert consistency | Passed | Scan/alert rollback together, repeated fixture deduplication, pagination, acknowledgment persistence, failure episodes |
| Notification behavior | Passed with mocks | Disabled transport never connects; TLS and stable Message-ID; retry limit/terminal failure/manual retry |
| Backup and restore | Passed | WAL consolidation, private archive, retained scans/model files/users, excluded sessions, paused schedules, suppressed pending email, no overwrite, unsafe path/checksum rejection |
| Mounted token handling | Passed with local fake tokens | Explicit file read, bounded/single-line input, safe missing/invalid errors, CLI fallback only when no file configured |
| Phase 1/2 compatibility | Passed | Original rules, missing-field semantics, legacy snapshots, activity features, model persistence/evaluation and provider mapping remain covered |

Model holdout metrics remain synthetic: 78.95% precision, 25% recall, 2.22%
false-positive rate, and 90 missed anomalies out of 120. The fixed activity
comparator has higher recall. No real-world performance advantage is claimed.

## Verification limits

- **Docker image build and container startup were not run.** Docker Desktop was stopped; the user explicitly chose to run Docker later. Compose syntax/configuration passed.
- **New browser pages were not visually verified.** Browser connection tools previously failed. The Phase 1 overview was user-confirmed; no confirmation of Phase 2/3 layouts is assumed. Type checking/building cannot establish browser behavior or mobile layout quality.
- **Live-port smoke checks were not completed in this session.** Local socket restrictions previously blocked server/browsing tools. The updated script is provided for the user's running server. Automated API flows use in-process ASGI routing, real middleware, persistence, and lifespan initialization.
- **No live AWS/Azure/GCP account scan.** Cloud mappings, partial failures, bounds, credential destination checks, and token-file behavior are validated with mocks/local fake files. Real permissions/network/credential expiry need a configured account.
- **No real SMTP delivery.** TLS/transport, outbox state, backoff, and failures are mocked. Sender acceptance, recipient delivery, and operational provider limits remain unverified.
- **Hosted CI has not executed here.** GitHub Actions includes backend/frontend checks and a Docker startup smoke job. Configuring a job is not evidence that it has passed.
- Phase 3 changes remain local and uncommitted in this session. No GitHub push, public deployment, or cloud mutation was performed.

## Manual runtime checklist

```bash
make check
make create-admin
bash scripts/demo.sh
# In another terminal:
make smoke
.venv/bin/python scripts/smoke_test.py --authenticated
```

For Docker use the commands in [deployment.md](deployment.md), with administrator
bootstrap inside the container.

- [ ] Sign in with the account you created; verify logout and returning to the login screen.
- [ ] Run a synthetic scan and inspect all 18 resources, 19 findings, and source/method labels.
- [ ] Inspect Activity analysis and Model lab, including false negatives and comparator metrics.
- [ ] Create a paused synthetic schedule, run it now, and inspect its successful run/new history entry.
- [ ] Enable it, wait for its interval, refresh, then pause it; restart the service and confirm schedules/history persist.
- [ ] Verify repeated demo scans do not duplicate the same finding alerts.
- [ ] Acknowledge an alert; verify review status survives reopening and does not change finding triage.
- [ ] Create viewer/analyst accounts; verify viewer inspection and analyst scan/triage controls.
- [ ] Change a user's role or password and confirm their prior session ends.
- [ ] Import configuration-only/activity inventories, triage a finding, and export its report.
- [ ] Review keyboard navigation, focus trapping, filters, sign-in forms, and narrow/mobile layouts.
- [ ] Start Docker later, verify non-root/read-only startup, bootstrap, readiness, volume persistence, and graceful shutdown.
- [ ] Back up and restore into a fresh directory; verify paused schedules and renewed sign-in before re-enabling.

Live collection and SMTP verification are optional operator steps that require
explicit local credentials/configuration. They are not required for the
synthetic Phase 3 workflow.
