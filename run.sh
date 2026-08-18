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
(cd backend && ../.venv/bin/uvicorn nexusrank.api:app --port 8000 --reload) &
(cd frontend && npm run dev) &
echo "NexusRank → UI http://localhost:5173   API http://localhost:8000/docs"
wait
