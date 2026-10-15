# Phase 3: monitoring, access, and local deployment

> Historical implementation milestone. For current behavior and deployment, see
> [README](../README.md), [architecture](architecture.md), and [deployment](deployment.md).

The abstract does not provide phase boundaries. The user authorized Phase 3
following the foundation and collection/ML phases, and selected a **local Docker
package and deployment instructions**. No cloud accounts are configured; use
synthetic scans and mocked provider/notification responses for validation.

## Implemented scope

| Deliverable | Implemented behavior |
| --- | --- |
| Authentication | Required sign-in; local first-admin CLI; salted scrypt passwords; opaque expiring sessions |
| Authorization | Shared workspace with administrator, analyst, and viewer permissions enforced by the API |
| Account management | Create users, change roles, disable access, own password change, local recovery, last-admin protection |
| Monitoring | Persisted synthetic/live schedules, explicit collection scope, intervals, pause/enable, manual run, UTC due times |
| Worker reliability | Single process lock, transactional claims, bounded operation serialization, backoff, interrupted-run recovery |
| Alert inbox | Finding, partial-coverage, and monitoring-failure alerts; deduplication; review acknowledgment; pagination |
| External notification | Optional TLS SMTP; private password file; durable retry state, bounded attempts, administrator retry |
| Audit records | Login, account, scan, model, schedule, triage, alert, delivery, and report-export actions |
| Operational tools | Public liveness/readiness, local smoke checks, session-free backups, safe offline restore |
| Deployment | Multi-stage Docker image, non-root runtime, read-only filesystem, loopback port, persistent named volume |
| Interface | Sign-in/setup, Monitoring, Alert inbox, Team & access; role-aware controls and periodic refresh |

Phase 1/2 rules, model behavior, legacy snapshots, imports, provenance, and honest
synthetic metrics remain intact. This is a local single-workspace application,
not a distributed or multi-tenant security service.

## Acceptance evidence

Automated tests exercise private API rejection, viewer/analyst/admin boundaries,
CSRF checks, session expiry and revocation, last-admin safeguards, schedule claim
races, pause/defer/backoff, interrupted jobs, atomic scan/alert writes, deduplication,
alert review, mocked SMTP/TLS, retry limits, and backup/restore protections.
TypeScript and the frontend production build pass. Compose configuration passes.
See [validation.md](validation.md) for the actual counts and remaining checks.

Docker Desktop was stopped. The user chose to run Docker later, so no image build
or container execution is claimed. The packaged CI Docker job is configured but
has not been executed in this session. Browser automation remains unavailable;
the new sign-in and operational pages need a manual visual check.

## Boundary and limitations

- No public hosting, real notification delivery, live-account scan, or cloud mutation.
- Schedules run while the one local service is running; no execution while it is stopped.
- One scheduled job per worker tick; missed intervals coalesce to a single run.
- All roles see the same workspace; no tenant/account isolation or SSO/MFA integration.
- Permanent finding fingerprints suppress repeat alerts; a recurring identical issue does not create a fresh alert episode.
- SMTP is at-least-once: a crash after server acceptance can produce a duplicate message on retry.
- Database records and completed model versions grow without automatic retention cleanup.
- Synthetic Isolation Forest recall remains 25%; no accuracy improvement is claimed.
- Full cloud-policy evaluation, automatic remediation, distributed execution, and real-incident evaluation remain outside scope.

## Start and review

Use the [README](../README.md) for host setup and the
[deployment guide](deployment.md) for Docker. Create an administrator through the
local CLI, sign in, run a synthetic scan, and inspect the 19 findings/alerts.
Create a paused synthetic schedule in Monitoring, select **Run now**, inspect the
saved run and scan, then enable it if desired. Repeated fixture scans add history
without duplicating the same finding alerts. In Team & access, create a viewer
and analyst to verify their permitted actions. Alert acknowledgment and finding
triage are separate actions. Optional SMTP remains off unless configured.
