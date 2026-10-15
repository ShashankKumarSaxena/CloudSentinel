#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
REQUIREMENTS=backend/requirements.txt
case "${1:-demo}" in
  demo) ;;
  --production) REQUIREMENTS=backend/requirements-production.txt ;;
  --dev) REQUIREMENTS=backend/requirements-dev.txt ;;
  *) printf 'Usage: bash scripts/setup.sh [demo|--production|--dev]\n' >&2; exit 2 ;;
esac
python3 -m venv .venv
.venv/bin/python -m pip install -r "$REQUIREMENTS"
npm --prefix frontend ci
printf '\nDependencies installed. See README.md for the offline demo and docs/deployment.md for production setup.\n'
