#!/usr/bin/env bash
# Re-run the PPO sensor-fault experiment (missing, biased, stuck) with the current twin.
# Usage: ./scripts/run_sensor_faults.sh [--model-id <id>]   (default: most recent trained model)
# Add --twin-bias none to reproduce the pre-bias-handling results in docs/results/sensor_faults.md.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd)/packages/irrivise_core:$(pwd)/services/api" MPLCONFIGDIR="$(pwd)/.cache/matplotlib"
for mode in missing biased stuck; do
  .venv/bin/python scripts/run_experiment.py --config "configs/experiments/sensor_fault_${mode}.yaml" "$@"
done
echo "Outputs: artifacts/experiments/cli-*/ (results.csv, summary.json, manifest.json per mode)."
