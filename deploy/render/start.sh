#!/bin/sh
# Render injects RENDER_EXTERNAL_HOSTNAME/URL and PORT; the app requires an explicit host allowlist.
set -eu
: "${RENDER_EXTERNAL_HOSTNAME:?RENDER_EXTERNAL_HOSTNAME is required}"
export CLOUDSENTINEL_ALLOWED_HOSTS="${RENDER_EXTERNAL_HOSTNAME}"
export CLOUDSENTINEL_PUBLIC_URL="${RENDER_EXTERNAL_URL:-https://${RENDER_EXTERNAL_HOSTNAME}}"
python scripts/bootstrap_hosted_demo.py
# Render's edge proxy terminates TLS; the container is reachable only through it.
exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-10000}" --workers 1 \
    --proxy-headers --forwarded-allow-ips '*' --no-access-log --no-server-header \
    --limit-concurrency 64 --timeout-graceful-shutdown 25
