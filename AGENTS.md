# Project instructions

## Purpose and production modernization
Build the AI-Based Automated Multi-Cloud Vulnerability Detector described in
`Cloud_Vulnerability_Detector_ProblemStatement_Abstract_1.docx`.
The user has authorized elevating the completed Phase 1–3 application into a
maintainable self-hosted solution for a single organization, with production
configuration, approved cloud accounts, reliable jobs, operational safeguards,
and professionally formatted source. Preserve a separate runnable demo mode.
This explicitly expands the prior Phase 3 boundary. Real cloud credentials are
not configured here. Do not publish, mutate infrastructure, or send notifications
implicitly. Never claim production validation, enterprise certification, or
real-world ML accuracy without evidence.

## Stack and layout
- `backend/`: Python 3.12+, FastAPI, Pydantic; PostgreSQL production, SQLite demo.
  Separate `api`, `core`, `domain`, `services`, `repositories`, and `infrastructure`.
- `frontend/`: React, TypeScript, Vite, CSS; `app`, `features`, `shared`, `styles`.
- `deploy/production/`: isolated PostgreSQL/worker/API/HTTPS deployment.
- `config/`: disabled account metadata examples and read-only permission templates.
- `data/demo_inventory.json`: synthetic cross-cloud configurations.
- `docs/`: scope, architecture, setup instructions, validation evidence.
- `scripts/`: repeatable setup, development, and verification commands.

## Working conventions
- Keep the demo local-first; production uses explicit deployment configuration. Never collect cloud credentials in the browser.
- Production cloud credentials come from provider workload identity/role chains
  or explicit federated token files mounted read-only on the worker. Legacy CLI
  adapters are for opt-in local development.
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
Run formatter checks and `npm run check` and `npm run build` in `frontend/`.
Run `python3 -m unittest discover -s backend/tests -v` from the project root.
Run `python3 scripts/smoke_test.py` with the local API running.
Verify the main demo flow in a browser when browser tools are available.
Test changes to rules, validation, persistence, and imports. UI-only edits need
type checking, a production build, and visual review, not mirror-image tests.

## Handoff
Keep README and operating documentation accurate; phase records are historical. Document what actually works,
what is synthetic, and any blocked step. Never claim GitHub publication,
browser verification, a live cloud scan, or ML validation without evidence.
