# Contributing

Use Python 3.12+ and Node.js 22.12+ (CI uses Node 24). From the repository root:

```bash
bash scripts/setup.sh --dev
make create-admin
make dev
```

Keep real accounts/credentials out of development. Demo mode uses synthetic data
and SQLite; approved collector tests use SDK stubs or mocked transports. There is
no default administrator. Read [AGENTS.md](AGENTS.md) for project conventions.

## Source conventions

Use four spaces in Python, two in TypeScript/CSS/JSON/YAML, and real tabs only in
Make recipes. Black 24.10.0 and Prettier 3.6.2 define formatting. Prefer descriptive
names, small functions, explicit service boundaries, and comments explaining an
invariant or tradeoff. Do not comment every obvious statement.

Keep HTTP request/response concerns under `api`, deployment validation under
`core`, business inputs/rules under `domain`, orchestration under `services`, and
external systems under `infrastructure`. SQL migrations are versioned per backend;
add a new migration for a released schema change. Frontend changes belong to the
relevant feature; reuse shared API contracts and UI components.

## Verification

```bash
make format
make check
make docker-config
```

Tests run in temporary local workspaces. Optional integration checks require:

```bash
# Use a disposable PostgreSQL database with CREATE SCHEMA permission.
# Set its private URL in your environment; never use a production workspace.
.venv/bin/python -m unittest backend.tests.test_postgresql_integration -v
.venv/bin/python -m unittest backend.tests.test_oidc_integration -v
```

The PostgreSQL tests read `CLOUDSENTINEL_TEST_DATABASE_URL`, create unique test
schemas, and clean them up. OIDC tests use a local mock transport and signed test
tokens with Authlib/HTTPX; they do not contact an identity provider. GitHub Actions
installs production/development dependencies and supplies PostgreSQL for these
checks. A configured workflow is not evidence that hosted CI has run.

Add meaningful tests for authorization, validation, rule mappings, transaction
boundaries, migration/recovery changes, and provider coverage. UI-only changes
need type/build checks and browser review. Inspect the demo and empty production
workspace at narrow and wide sizes when browser tools are available.

Before requesting review, describe the user-visible behavior, validation evidence,
and any unverified deployment assumptions. Never commit local accounts, cloud
credentials, runtime databases, backup archives, or generated model files.
