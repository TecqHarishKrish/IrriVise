#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ ! -d .venv ]; then "$PYTHON_BIN" -m venv .venv; fi
.venv/bin/python -m pip install -r services/api/requirements.txt
if command -v npm >/dev/null 2>&1; then
  (cd apps/web && npm install)
elif command -v pnpm >/dev/null 2>&1; then
  CI=true pnpm install --dir apps/web --frozen-lockfile --prefer-offline
else
  echo "Node.js package manager missing: install supported Node.js and npm" >&2
  exit 1
fi
PYTHONPATH=packages/irrivise_core .venv/bin/python scripts/sample_data.py
echo "Setup finished. Start with ./scripts/dev.sh"
