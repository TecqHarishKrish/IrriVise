#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export MPLCONFIGDIR="$(pwd)/.cache/matplotlib"
mkdir -p "$MPLCONFIGDIR"
PYTHONPATH=packages/irrivise_core:services/api .venv/bin/python -m pytest tests -q
(cd apps/web && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/vite build)
