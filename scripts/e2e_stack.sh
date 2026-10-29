#!/usr/bin/env bash
# Isolated stack for Playwright: fresh data root, API :8010, worker, Vite :5183.
set -euo pipefail
cd "$(dirname "$0")/.."
export IRRIVISE_DATA_ROOT="${IRRIVISE_E2E_ROOT:-$(pwd)/.cache/e2e-data}"
rm -rf "$IRRIVISE_DATA_ROOT" && mkdir -p "$IRRIVISE_DATA_ROOT"
export PYTHONPATH="$(pwd)/packages/irrivise_core:$(pwd)/services/api" MPLCONFIGDIR="$(pwd)/.cache/matplotlib"
export IRRIVISE_CORS_ORIGINS="http://127.0.0.1:5183" IRRIVISE_API_URL="http://127.0.0.1:8010"
pids=()
trap 'for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done' EXIT INT TERM
.venv/bin/python -m uvicorn irrivise_api.main:app --host 127.0.0.1 --port 8010 --log-level warning & pids+=($!)
for _ in $(seq 1 60); do curl -fs http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 0.5; done
.venv/bin/python -m irrivise_api.worker > "$IRRIVISE_DATA_ROOT/worker.log" 2>&1 & pids+=($!)
cd apps/web && ./node_modules/.bin/vite --host 127.0.0.1 --port 5183 --strictPort & pids+=($!)
wait -n "${pids[@]}"
