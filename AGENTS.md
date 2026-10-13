# Project instructions

## Purpose and Phase 1 boundary
Build the AI-Based Automated Multi-Cloud Vulnerability Detector described in
`Cloud_Vulnerability_Detector_ProblemStatement_Abstract_1.docx`.
The abstract does not define phases. The current Phase 1 is a working foundation:
normalized configuration inventory, deterministic configuration checks, SQLite
scan history, finding triage, and a responsive security dashboard.

Do only Phase 1 unless the user explicitly expands the scope. ML anomaly
detection, activity ingestion, live AWS/Azure/GCP API collectors, continuous
monitoring, authentication, and automatic remediation belong to later phases.
Never represent fixture data as live cloud data or deterministic rules as AI.

## Stack and layout
- `backend/`: Python 3.12+, FastAPI, Pydantic, SQLite; business logic in services.
- `frontend/`: React, TypeScript, Vite, CSS; accessible responsive UI.
- `data/demo_inventory.json`: synthetic cross-cloud configurations.
- `docs/`: scope, architecture, setup instructions, validation evidence.
- `scripts/`: repeatable setup, development, and verification commands.

## Working conventions
- Keep this project local-first. Never collect cloud credentials in the browser.
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
Keep README and `docs/phase-1.md` accurate. Document what actually works,
what is synthetic, and any blocked step. Never claim GitHub publication,
browser verification, a live cloud scan, or ML validation without evidence.
