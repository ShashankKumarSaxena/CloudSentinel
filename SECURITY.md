# Reporting security issues

Do not include secrets, account evidence, exploit tokens, or sensitive logs in
public issues. Contact the repository owner through a private channel agreed by
your organization. If GitHub private vulnerability reporting is enabled on the
repository, use its Security reporting interface. No monitored security email,
response-time guarantee, or managed support service is established by this code.

Include the affected revision, deployment mode, prerequisites, impact, and a
minimal reproduction using synthetic data. Rotate exposed credentials and
revoke affected sessions through your organization's incident process.

Before deployment, review [security design](docs/security.md),
[deployment](docs/deployment.md), and [validation](docs/validation.md). Dependency
pins and container tags need regular review; installing this package does not
establish an audited or certified security posture.
