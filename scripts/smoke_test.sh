#!/usr/bin/env bash
# Offline verification: backend + science tests, frontend lint/typecheck/unit tests/build, sample-data checksum.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd)/packages/irrivise_core:$(pwd)/services/api" MPLCONFIGDIR="$(pwd)/.cache/matplotlib"
.venv/bin/python scripts/sample_data.py --check
.venv/bin/python -m pytest -q
(cd apps/web && npm run lint && npm run typecheck && npx vitest run && npm run build)
echo "Smoke test passed."
