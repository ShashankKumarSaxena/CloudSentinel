#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
PROJECT_PYTHON="python3"
if [[ -x .venv/bin/python ]]; then PROJECT_PYTHON="$PROJECT_ROOT/.venv/bin/python"; fi
if ! "$PROJECT_PYTHON" -c 'import fastapi, uvicorn, pydantic' 2>/dev/null; then
  printf 'Backend dependencies are missing. Run: bash scripts/setup.sh\n' >&2
  exit 1
fi
if [[ ! -d frontend/node_modules ]]; then
  printf 'Frontend dependencies are missing. Run: bash scripts/setup.sh\n' >&2
  exit 1
fi
npm --prefix frontend run build
printf '\nCloudSentinel mentor demo: http://127.0.0.1:8000\nAPI documentation: http://127.0.0.1:8000/docs\nPress Ctrl+C to stop.\n\n'
exec "$PROJECT_PYTHON" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
