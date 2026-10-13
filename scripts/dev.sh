#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
PROJECT_PYTHON="python3"
if [[ -x .venv/bin/python ]]; then PROJECT_PYTHON="$PROJECT_ROOT/.venv/bin/python"; fi
"$PROJECT_PYTHON" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
cleanup() { kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
"$PROJECT_PYTHON" scripts/wait_for_api.py
npm --prefix frontend run dev
