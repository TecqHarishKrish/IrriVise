#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
if [ ! -x .venv/bin/python ] || [ ! -d apps/web/node_modules ]; then echo "Run ./scripts/setup.sh first" >&2; exit 1; fi
if ! command -v node >/dev/null 2>&1; then echo "Node.js missing" >&2; exit 1; fi
export PYTHONPATH="$(pwd)/packages/irrivise_core:$(pwd)/services/api"
export MPLCONFIGDIR="$(pwd)/.cache/matplotlib"
mkdir -p "$MPLCONFIGDIR"
.venv/bin/python -m uvicorn irrivise_api.main:app --host 127.0.0.1 --port 8000 --log-level warning & API_PID=$!
.venv/bin/python -m irrivise_api.worker & WORKER_PID=$!
(cd apps/web && ./node_modules/.bin/vite --host 127.0.0.1) &
WEB_PID=$!
trap 'kill "$API_PID" "$WORKER_PID" "$WEB_PID" 2>/dev/null || true' EXIT INT TERM
echo "IrriVise API http://127.0.0.1:8000/docs | Web http://127.0.0.1:5173"
wait "$WEB_PID"
