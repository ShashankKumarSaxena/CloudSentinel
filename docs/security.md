# Access and security design

Phase 3 provides local accounts for one shared workspace. Authentication is
required for private APIs, API schema/docs, and data exports. Static frontend
files and public liveness/readiness/setup/login routes remain accessible so a
user can sign in. No switch disables authentication.

## Accounts and passwords

The first administrator is created through `scripts/manage_users.py create-admin`
with an interactive password prompt. There are no default credentials or public
bootstrap API. Administrators create additional accounts through Team & access.
Passwords must contain 12–256 characters. Usernames are case-insensitive and
unique. The last enabled administrator cannot be disabled or demoted.

Passwords use a random 16-byte salt and stdlib scrypt with N=2^15, r=8, p=3.
Hashes remain on the server and never appear in user responses. These parameters
are among the supported combinations in the
[OWASP Password Storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
Unknown users undergo a dummy password check. Invalid credentials use a generic
error. Five failures per client/username in a 15-minute window block further
attempts for that window. Password checks for login are serialized to bound
memory use. This local throttle is not a distributed perimeter protection system.

Password changes require the current password and revoke all account sessions.
Role/access changes also revoke sessions. Local CLI password recovery is an
operator capability for someone who already controls the machine/data directory.
Disabling an account preserves its history.

## Sessions and browser protections

Sessions use random opaque 32-byte tokens; SQLite stores only their SHA-256
hashes. Cookies are HttpOnly and SameSite=Strict, scoped to the workspace origin.
Sessions expire after eight hours or 30 minutes without authenticated API
requests. Visible dashboard polling counts as activity; this is not a keyboard
inactivity timer. At most five sessions remain active per account.
Logout revokes the selected session server-side. Client CSRF state stays in
memory and is not stored in localStorage.

Private write requests require the separate session CSRF token in the
`X-CSRF-Token` header. Browser-origin checks reject unrelated origins on writes,
including login. The host dev workflow permits the local Vite origin. Explicit
allowed hosts prevent arbitrary Host headers. Responses include no-sniff,
frame-denial, same-origin referrer policy, and a self-origin CSP; API responses
use no-store. Inline styles remain permitted for existing computed visuals;
inline scripts are not permitted by the production API CSP.

The supplied loopback HTTP deployment uses `CLOUDSENTINEL_SECURE_COOKIES=0`.
HTTPS deployments require secure cookies (`1`), which also enables HSTS.
See the [OWASP Session Management guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
and [CSRF Prevention guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
for the principles behind these controls.

## Permissions

| Operation | Viewer | Analyst | Administrator |
| --- | --- | --- | --- |
| Inspect workspace data, schedules, alerts; export reports | Yes | Yes | Yes |
| Run/import/collect scans; triage findings; acknowledge alerts | — | Yes | Yes |
| Manage users/schedules; run schedules manually; train models; retry email; read audit | — | — | Yes |
| Change own password; sign out | Yes | Yes | Yes |

The API enforces permissions independently of hidden/disabled UI controls.
Accounts share resource visibility. There is no tenant isolation, account-level
permission partition, SSO, or multifactor authentication in this phase.

## Data and secrets

Cloud credentials are accepted only through local provider SDK/CLI chains or
explicit server-side token file settings. Collection forms contain identifiers
and scope, never tokens or access keys. Token files have a 16 KiB bound and
reject empty/multiline content. REST adapters restrict destinations to known
HTTPS provider hosts and reject redirects/pagination to unrelated destinations.
Provider exception strings, raw credential responses, and passwords are not
returned through the API or audit log.

SQLite uses parameterized SQL, bounded validated imports, short write
transactions, and immutable scan evidence. Default runtime directories are
private, the database is mode 600, and generated model artifacts are mode 600.
External SMTP is opt-in with reviewed recipients and TLS. SMTP passwords come
from private files. Credentials and runtime files are excluded from Git and
Docker build context. Container mounts must be configured explicitly.

Model artifacts use trusted local joblib files. Uploaded data is validated JSON,
not executable model files. A checksum in a backup detects damage; it does not
make an untrusted archive safe. Backups include password hashes/cloud evidence
and need private storage or external encryption. Restore your own trusted backups.

## Scope of assurance

Tests cover anonymous access, roles, CSRF, cookie flags, expiry, revocation,
last-admin protection, throttling, and sanitized error paths. Docker runtime,
live-cloud credentials, real SMTP, and browser flows still require the validation
steps in [validation.md](validation.md). This release has not undergone a
penetration test, independent security audit, or compliance certification.
It does not encrypt the SQLite database at rest, implement automatic remediation,
or establish production safety for the synthetic-trained anomaly model.
