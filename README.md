# IrriVise — Think Before You Water

IrriVise is a locally runnable research platform for **CARAT — Counterfactual Action-Regret and Adaptive Twin Correction**, an irrigation decision method proposed by this project. A PPO irrigation policy acts on an uncertain digital twin of the field; CARAT estimates how much a soil-moisture reading could change the decision (estimated regret and value of information), requests a reading only when that is worth its cost, corrects the twin, and passes the action through a risk manager. Everything is evaluated against baselines on a **simulated** farm.

> **Honesty notice.** All farm outcomes are simulated. The offline dataset is **synthetic demonstration weather**. "Yield proxy" comes from the fast surrogate (FAO-33); "AquaCrop yield" replays a schedule in AquaCrop-OSPy with default parameters. Neither is a measured yield, and nothing here is field-validated. CARAT is a proposed method — the experiments can and do show where it does not help.

## Features

* **11 pages**: Command Center, Projects & Fields, Weather & Data Studio, Digital Twin Studio, Irrigation Simulator, Model Training Lab, CARAT Decision Lab, Experiment Benchmark, Insights & Analytics, Report & Export Center, Settings & Help. Responsive (1440/1280/768/390 px), light/dark theme, keyboard accessible, every chart has a data-table, CSV and SVG alternative.
* **Science core**: FAO-56 root-zone water balance with explicit mass balance, hidden reference farm with random soil parameters, 20-member ensemble twin with Kalman correction, budgeted noisy sensor with dropout/bias/stuck/delay faults, climatology + persistence forecasts, CARAT regret/VOI engine, risk manager, Gymnasium environment, Stable-Baselines3 PPO with validation-based checkpoint selection, AquaCrop-OSPy schedule evaluation.
* **Research workflow**: matched experiments over seasons × seeds × observation budgets × sensor noise, baselines B0–B5, ablations A5/A6, paired bootstrap CIs and Wilcoxon tests, deterministic "What did the data show?" summaries, failed runs listed.
* **Engineering**: FastAPI `/api/v1` + OpenAPI at `/docs`, SQLite + SQLAlchemy 2 + Alembic, separate durable worker (spawned child per job, heartbeats, cancellation, crash recovery), SSE progress with polling fallback, verified exports (ZIP/CSV/JSON/printable HTML with SVG charts) and reproducibility manifests.
* **Data**: deterministic 20-year synthetic fixture (offline); NASA POWER daily ingestion with FAO-56 Penman–Monteith ET₀, caching and bounded retries; CSV import with validation and quarantine.
* **No paid services, no API keys, no accounts, no sensors.**

## Requirements

* Python **3.12** (3.11 should work; tested on 3.12.13, Linux x86-64)
* Node.js **20+** (tested on 22.22) with npm
* ~3 GB disk for PyTorch (the CPU wheel is used when the PyTorch index is reachable)

## Install and run

```bash
./scripts/setup.sh
```

```bash
./scripts/dev.sh
```

Then open http://127.0.0.1:5173 (API docs: http://127.0.0.1:8000/docs). `dev.sh` starts the API, the worker and the Vite server, refuses to start if a port is busy, and stops all three on Ctrl+C. Windows: `scripts/setup.ps1` and `scripts/dev.ps1` (not tested in the build environment).

Manual start (three terminals, from the repository root):

```bash
export PYTHONPATH=$PWD/packages/irrivise_core:$PWD/services/api
.venv/bin/python -m uvicorn irrivise_api.main:app --host 127.0.0.1 --port 8000
```

```bash
export PYTHONPATH=$PWD/packages/irrivise_core:$PWD/services/api
.venv/bin/python -m irrivise_api.worker
```

```bash
cd apps/web && npm run dev
```

## Offline walkthrough

1. First launch shows **Welcome to IrriVise** → *Explore sample field*. This creates a maize / sandy-loam field near Tiruchirappalli using the synthetic weather and queues a fixed-schedule run.
2. **Irrigation Simulator**: inspect KPIs, rainfall/irrigation, twin soil-water band and stress charts; step through the saved daily records.
3. **Model Training Lab**: queue the *Quick smoke* preset (≈ 20 s). It is a functional test, not a good policy. *Standard CPU* (150k steps × 3 seeds) takes ≈ 30 min on 4 cores.
4. Simulator → method *P · Full CARAT* with the trained model (or *CARAT planner* without PPO).
5. **CARAT Decision Lab**: replay any day — candidate actions, plausible states (Plotly heatmap), regret and VOI, twin correction, risk manager, and a plain explanation generated from the trace. Toggle post-run evaluation to see the hidden reference.
6. **Experiment Benchmark**: select methods, seeds, budgets and noise levels; results show paired differences with CIs.
7. **Report & Export Center**: ZIP bundle or printable HTML report with the reproducibility manifest.

## Tests

```bash
.venv/bin/python -m pytest -q
```

```bash
cd apps/web && npm run lint && npm run typecheck && npx vitest run && npm run build
```

```bash
cd apps/web && npx playwright test
```

`./scripts/smoke_test.sh` runs the sample-data checksum, all Python tests and all frontend checks. Playwright starts its own isolated stack on ports 8010/5183 (`scripts/e2e_stack.sh`).

## Command-line research workflow

```bash
.venv/bin/python scripts/train_ppo.py --preset cpu_quick --dataset sample --seed 42
```

```bash
.venv/bin/python scripts/run_experiment.py --config configs/experiments/baselines.yaml
```

See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for exact regeneration commands and recorded results.

## NASA POWER

In **Weather & Data Studio**, enter coordinates and a past date range (≤ 25 years) and queue a download. The worker calls only the official daily point endpoint, caches the response, converts units, computes FAO-56 ET₀ and validates the series. If the network is unavailable the job fails with a clear message and the synthetic dataset remains usable. Attach the new dataset to a scenario to simulate or train on it. *NASA POWER could not be reached from the build environment (egress blocked), so live ingestion was verified only against recorded/mocked payloads.*

## Troubleshooting

| Symptom | Fix |
|---|---|
| Banner "Worker not started/offline" | Start `python -m irrivise_api.worker` (dev.sh does this); jobs stay queued until then |
| "Port 8000 is already in use" | Stop the other process or `API_PORT=8001 WEB_PORT=5174 ./scripts/dev.sh` |
| PPO methods disabled | Train a model first; PPO methods never show placeholder recommendations |
| Job `interrupted` | The worker stopped while it ran; partial artifacts are discarded — re-queue it |
| Export refused (`artifact_modified`) | A saved file no longer matches its recorded SHA-256; regenerate the run |
| Reset demo state | Settings & Help → *Reset sample data* (never deletes your own data) |

## Limitations

See [METHODOLOGY.md §12](METHODOLOGY.md#12-limitations) and [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md). In short: simulated farm, uncalibrated surrogate, climatology forecasts, model-based regret/VOI, synthetic data offline, local single-user mode without authentication.

## Documentation

[ARCHITECTURE.md](ARCHITECTURE.md) · [METHODOLOGY.md](METHODOLOGY.md) · [REPRODUCIBILITY.md](REPRODUCIBILITY.md) · [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) · original specification: [IRRIVISE_CODEX_MASTER_PROMPT.md](IRRIVISE_CODEX_MASTER_PROMPT.md)

Weather data attribution: NASA Langley Research Center POWER Project (https://power.larc.nasa.gov), when used.
