#!/usr/bin/env bash
# Idempotent setup for macOS/Linux: Python venv + pinned backend deps, frontend deps, sample data check, DB migration.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PYTHON_BIN="$candidate"; break; fi
  done
fi
"$PYTHON_BIN" -c 'import sys; assert (3, 11) <= sys.version_info[:2] <= (3, 12), "Python 3.11 or 3.12 required (tested: 3.12)"' \
  || { echo "Set PYTHON_BIN to a Python 3.11/3.12 interpreter" >&2; exit 1; }
[ -d .venv ] || "$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip >/dev/null
# CPU-only torch keeps the install small where the PyTorch index is reachable; falls back to PyPI.
.venv/bin/python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu 2>/dev/null || true
.venv/bin/python -m pip install -r services/api/requirements.txt
command -v node >/dev/null 2>&1 || { echo "Node.js 20+ is required for the web app" >&2; exit 1; }
(cd apps/web && npm install --no-audit --no-fund)
export PYTHONPATH="$(pwd)/packages/irrivise_core:$(pwd)/services/api" MPLCONFIGDIR="$(pwd)/.cache/matplotlib"
.venv/bin/python scripts/sample_data.py --check
.venv/bin/python -c "from irrivise_api.db.session import migrate; print('database schema revision', migrate())"
echo "Setup finished. Start everything with ./scripts/dev.sh"
