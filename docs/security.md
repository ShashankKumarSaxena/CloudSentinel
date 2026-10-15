# Security design

## Organization and access

CloudSentinel supports one organization with shared cloud evidence. Viewer,
analyst, and administrator permissions are enforced by server middleware.
There is no tenant or account-level visibility isolation.

| Operation | Viewer | Analyst | Admin |
| --- | --- | --- | --- |
| Read scans, coverage, jobs, alerts, schedules, models; export reports | Yes | Yes | Yes |
| Import/collect; cancel pending jobs; triage; acknowledge alerts | — | Yes | Yes |
| Manage users/schedules, read audit, retry email | — | — | Yes |
| Train models through the API, in demo mode | — | — | Yes |
| Change own local password; sign out | Yes | Yes | Yes |

The first administrator is created only through the interactive local CLI.
There are no default credentials or unauthenticated bootstrap routes. The last
enabled administrator and last local recovery administrator cannot be removed.

Local passwords require 12–256 characters and use scrypt (N=2^15, r=8, p=3), a
random 16-byte salt, and serialized hashing to bound memory pressure. Unknown
users receive a dummy hash check. Five failed client/username attempts within
15 minutes block further attempts for that window. Put an appropriate access
boundary/rate limiter in front of an exposed installation.

Optional OIDC delegates corporate authentication and MFA to the configured IdP.
Authlib validates the authorization-code/PKCE flow and signed identity token.
Only an explicitly approved **issuer + subject** maps to a local enabled user;
email addresses and identity-provider role claims cannot auto-provision access.
Local roles remain authoritative. Identity linking revokes existing sessions and
turns that user into SSO-only access. Keep a separate local recovery administrator.

## Sessions and browser boundary

Opaque random 32-byte session tokens live in HttpOnly, SameSite=Strict cookies;
only SHA-256 token hashes are persisted. Production cookies require HTTPS, with
one-hour absolute and 15-minute idle expiry by default (demo: eight hours/30
minutes). Polling counts as activity. Five concurrent sessions per user are kept.
Password/role/access changes revoke sessions. Logout revokes its session.
OIDC has a separate signed, short-lived SameSite=Lax state cookie for the
cross-site callback; raw IdP tokens never enter the dashboard.

Private writes require a session CSRF token and exact configured origin when an
Origin header is present. Production requires explicit allowed hosts, secure
cookies, an HTTPS origin, PostgreSQL, and a separate worker. Security headers
include CSP, frame denial, no-sniff, same-origin referrers, and HSTS over HTTPS.
Inline styles support computed visuals; inline scripts are prohibited. API
responses use no-store. Static application files contain no cloud evidence.

## Cloud credentials and data

The operator-owned registry approves explicit accounts and regions. The browser
cannot add accounts or submit credentials. Production credentials are acquired
only by the worker: AWS role chains/assumed roles with external ID, explicit Azure
managed/workload identity, or GCP workload identity/ADC and optional impersonation.
GCP private service-account keys and developer user credentials are rejected on
the approved path. Demo mode blocks cloud jobs unless an operator explicitly
opts into local collector development.

Collectors use fixed HTTPS provider hosts, reject redirects/unrelated pagination,
bound responses and retries, and issue no remediation calls. Resource/event
accounts are checked against approval before snapshots commit. Provider errors
are sanitized. Missing or inaccessible data remains unknown/partial.

Deployment secrets are file-backed, excluded from Git/build context, and not
accepted as UI fields. The default production PostgreSQL connection uses TLS
verify-full against a private CA. Caddy terminates browser HTTPS. API networking
is internal by default; optional OIDC adds identity-provider egress. Only the
worker mounts cloud identity files. Docker egress networks do not constitute a
provider-destination firewall; configure host/platform controls if required.

## Logs, storage, and recovery

Production request logs contain UTC time, request ID, route template, status,
and duration. Errors log exception type and code location, without provider
messages, request bodies, query strings, or credentials. Uvicorn access logging
is disabled to avoid logging authorization codes in callback URLs. Protect the
operator audit log and export it to your organization's logging system as needed;
it is not an externally immutable compliance ledger.

Backups contain sensitive evidence and password hashes. Checksums detect damage,
not authenticity; encrypt archives externally and restore only trusted backups.
Restores revoke sessions, pause schedules/jobs, and suppress queued email.
Trusted joblib artifacts can execute Python during loading: protect the model
volume and never install third-party artifacts from users.

There is no security certification or completed penetration test. Before exposing
a deployment, complete the [rollout checks](validation.md), review permissions,
rotate/restrict credentials, and test recovery in your environment. Report issues
using the process in [SECURITY.md](../SECURITY.md).
