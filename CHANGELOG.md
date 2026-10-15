# Changelog

## 1.0.0 — deployment foundation (unreleased)

- Separate offline demo and production startup policies; production starts empty.
- Operator-approved AWS/Azure/GCP account scopes and worker-only SDK credentials.
- Durable idempotent collection jobs, singleton ownership/fencing, recovery, and
  account-specific snapshot pointers.
- PostgreSQL adapter/pooling, versioned migrations, bounded history queries,
  transactional scan/alert evidence, and explicit retention maintenance.
- Optional corporate OIDC sign-in with pre-approved subjects and local roles.
- Configuration-finding recurrence and reopening on continuing failed checks.
- Separate API/domain/service/repository/infrastructure modules and frontend
  feature folders, consistent formatting, shared contracts, and targeted comments.
- PostgreSQL TLS/HTTPS Compose package, secret preparation, backup/restore tools,
  federation/SMTP overlays, operator guides, and integration test configuration.

This release has local unit/API/mocked-provider validation. New production
SDKs, PostgreSQL/OIDC integration, container runtime, and live cloud access still
require deployment verification. See `docs/validation.md`.

## 0.3.0 — monitoring and access

Local accounts, sessions/CSRF, roles, schedules, alert inbox, optional email,
audit records, SQLite backups, and demo Docker packaging.

## 0.2.0 — activity detection and collection

Isolation Forest activity scoring, held-out synthetic evaluation, versioned model
artifacts, and read-only AWS/Azure/GCP collector mappings.

## 0.1.0 — configuration workspace

Inventory validation, deterministic checks, findings/triage, history, reports,
and the synthetic multi-cloud dashboard.
