# Project instructions

## Purpose and Phase 3 boundary
Build the AI-Based Automated Multi-Cloud Vulnerability Detector described in
`Cloud_Vulnerability_Detector_ProblemStatement_Abstract_1.docx`.
The abstract does not define phases. Phase 1 established normalized inventory,
configuration checks, SQLite history, triage, and the dashboard. The user has
authorized Phase 3: persistent monitoring schedules, authenticated shared-workspace
access, administrator/analyst/viewer roles, alerts, operational audit logs, and
local Docker deployment. Retain Phase 1/2 configuration and Isolation Forest
behavior. Validate with synthetic data and mocked cloud APIs; no cloud accounts
are configured. Do not publish to a hosting service.

Do only Phase 3 unless the user explicitly expands the scope. Automatic
remediation, comprehensive policy evaluation, and real-incident validation remain
outside scope. Never represent synthetic data as live or synthetic evaluation as
real-world accuracy. Label rule and ML findings separately.

## Stack and layout
- `backend/`: Python 3.12+, FastAPI, Pydantic, SQLite; business logic in services.
- `frontend/`: React, TypeScript, Vite, CSS; accessible responsive UI.
- `data/demo_inventory.json`: synthetic cross-cloud configurations.
- `docs/`: scope, architecture, setup instructions, validation evidence.
- `scripts/`: repeatable setup, development, and verification commands.

## Working conventions
- Keep this project local-first. Never collect cloud credentials in the browser.
- Cloud credentials come only from local provider SDK/CLI credential chains or
  explicitly configured local token files mounted read-only into containers.
- Never load an uploaded pickle/model or expose tokens, raw API responses, or
  provider exception strings. Cloud collectors must not mutate infrastructure.
- Authentication must be enabled by default. Hash passwords, store only session
  token hashes, enforce expiry and CSRF, and check roles on the server.
- Bootstrap the first administrator only through the local CLI, without a
  default password. Keep credentials and tokens out of logs and Git.
- Persist schedules, alerts, retries, and audit records. Use one monitoring
  process per database, recover interrupted work, and never duplicate due jobs.
- External alert delivery is opt-in through local configuration. Do not send
  real notifications during implementation; validate with mocked transports.
- Preserve unknown fields and expose partial coverage and collection errors.
- Training, calibration, and evaluation samples must be disjoint. Never tune
  thresholds on the evaluation set or include labels/identifiers as ML features.
- Do not deploy, scan a real account, or change cloud infrastructure implicitly.
- Validate imported inventory. Missing configuration must be reported as unknown,
  never treated as a passing check. Imports are bounded and atomic.
- Keep API contracts typed, errors useful, SQL parameterized, and secrets/logs
  out of Git. Keep fixture provenance visible on dashboards and exports.
- Keep scan snapshots immutable; finding disposition is a separate user action.
- Use UTC for stored timestamps and local formatting in the interface.
- Keep styling in CSS; provide keyboard focus, labels, and responsive layouts.
- Use product-focused language in the interface and documentation.
- Do not spawn subagents unless explicitly asked by the user.

## Verification
Run `npm run check` and `npm run build` in `frontend/`.
Run `python3 -m unittest discover -s backend/tests -v` from the project root.
Run `python3 scripts/smoke_test.py` with the local API running.
Verify the main demo flow in a browser when browser tools are available.
Test changes to rules, validation, persistence, and imports. UI-only edits need
type checking, a production build, and visual review, not mirror-image tests.

## Handoff
Keep README and phase documentation accurate. Document what actually works,
what is synthetic, and any blocked step. Never claim GitHub publication,
browser verification, a live cloud scan, or ML validation without evidence.
