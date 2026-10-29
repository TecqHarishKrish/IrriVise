#!/usr/bin/env bash
# Start API (127.0.0.1:8000), durable worker and Vite dev server (127.0.0.1:5173). Ctrl+C stops all three.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] && [ -d apps/web/node_modules ] || { echo "Run ./scripts/setup.sh first" >&2; exit 1; }
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
for port in "$API_PORT" "$WEB_PORT"; do
  if port_busy "$port"; then echo "Port $port is already in use; stop that process or set API_PORT/WEB_PORT" >&2; exit 1; fi
done
export PYTHONPATH="$(pwd)/packages/irrivise_core:$(pwd)/services/api" MPLCONFIGDIR="$(pwd)/.cache/matplotlib"
export IRRIVISE_API_URL="http://127.0.0.1:${API_PORT}"
mkdir -p .cache/logs
pids=()
cleanup() { trap - EXIT INT TERM; for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; wait 2>/dev/null || true; echo "IrriVise stopped."; }
trap cleanup EXIT INT TERM
.venv/bin/python -m uvicorn irrivise_api.main:app --host 127.0.0.1 --port "$API_PORT" --log-level warning & pids+=($!)
for _ in $(seq 1 60); do curl -fs "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 && break; sleep 0.5; done
.venv/bin/python -m irrivise_api.worker > .cache/logs/worker.log 2>&1 & pids+=($!)
(cd apps/web && ./node_modules/.bin/vite --host 127.0.0.1 --port "$WEB_PORT" --strictPort) & pids+=($!)
echo "IrriVise  web: http://127.0.0.1:${WEB_PORT}   API docs: http://127.0.0.1:${API_PORT}/docs   worker log: .cache/logs/worker.log"
wait -n "${pids[@]}"
