# Files not in the GitHub repository

Everything outside this folder is exactly the branch `claude/irrivise-end-to-end-t9d73t` at commit `ba1364c` (same as GitHub).

This folder holds working files from the 2026-10-29 sensor-bias session. They are not needed to run IrriVise.

| Path | What it is |
|---|---|
| `scripts/faultbench.py` | First version of the no-PPO fault bench (became `scripts/sensor_bias_bench.py`). Its output keys: reward = objective, reads = readings, rmse/bias = twin error in mm. |
| `scripts/rungrid.sh`, `scripts/savegrid.py` | Ran the validation tuning grid and wrote `docs/results/sensor_bias_tuning.json`. |
| `scripts/trace.py` | Prints innovations, gains and offset per reading for one season; this is how the negative-gain bug was found. |
| `raw_runs/validation_grid/` | Per-setting validation runs behind the tuning record (prior × drift). |
| `raw_runs/superseded_grid/` | Grid from the first, buggy filter (before the storage–offset decoupling fix). Kept for transparency; do not use. |
| `raw_runs/*` | before_test = code before the change; none/mon/aug = no handling / innovation monitor / augmented, on validation and test seasons. |

Not included, because none exist in this copy: trained PPO checkpoints (`artifacts/`, git-ignored). Retrain with
`python scripts/train_ppo.py --preset cpu_standard --dataset sample`. Python virtual environments and node_modules are
also left out; `scripts/setup.sh` (or `setup.ps1` on Windows) recreates them.

All outcomes are simulated.
