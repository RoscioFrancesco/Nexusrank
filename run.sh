#!/usr/bin/env bash
# One-command demo: seeds SQLite on first run, serves API on :8000 and UI on :5173.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip -q install -r backend/requirements.txt
fi
[ -d frontend/node_modules ] || (cd frontend && npm install --silent)

trap 'kill 0' EXIT
export NEXUSRANK_TOKEN="${NEXUSRANK_TOKEN:-$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)}"
# local only: bound to 127.0.0.1, no external requests, no analytics
(cd backend && ../.venv/bin/uvicorn nexusrank.api:app --host 127.0.0.1 --port 8000 --reload) &
(cd frontend && npm run dev -- --host 127.0.0.1) &
echo "NexusRank → UI http://127.0.0.1:5173   API locale protetta su 127.0.0.1:8000"
wait
