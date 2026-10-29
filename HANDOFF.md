# IrriVise / CARAT — handover document

_Last updated: 2026-10-29 (after adding sensor-bias handling). Use this to continue the work in a new chat or by hand._

## 1. Project in one paragraph

**IrriVise — Think Before You Water** is a local web platform for researching **CARAT** (Counterfactual Action-Regret and Adaptive Twin Correction), an irrigation decision method proposed by this project. A PPO reinforcement-learning policy decides daily irrigation (0/5/10/15/20 mm) from an uncertain **digital twin** of the soil (20 plausible states). Each day CARAT estimates how much could be lost by deciding without knowing the true soil state (estimated regret) and how much a soil-moisture reading would reduce that loss (value of information). It takes a reading only when that value exceeds its cost, corrects the twin with a Kalman update, and a risk manager enforces the daily and seasonal water limits. Everything runs on a **simulated** farm. Results are not field measurements.

Repository: https://github.com/TecqHarishKrish/IrriVise

## 2. Where the code is

| Item | State |
|---|---|
| Branch | `claude/irrivise-end-to-end-t9d73t` on GitHub, on top of `main` @ `3e5ecf4` |
| Get it | `git fetch origin claude/irrivise-end-to-end-t9d73t && git checkout claude/irrivise-end-to-end-t9d73t` |
| Merge | Open a pull request into `main`; the branch starts from `main`, so it fast-forwards. |
| Not in git | Trained PPO checkpoints (`artifacts/` is ignored). Retrain with `.venv/bin/python scripts/train_ppo.py --preset cpu_standard --dataset sample` (≈ 5 min/seed); the recorded model was seed 44 (`docs/results/model_5254f0b2-….json`). |

Commits, oldest first: `7445de6` platform rebuild · `4f3c9c8` tests, E2E, CLI, validation tuning, docs · `6d1327e` daily-reference fix and results · `f8e8ab8` reproducibility record · `d29e995` Python version, ignore rule · `640d682` handover · then sensor-bias handling (2026-10-29: code, then results and docs).

## 3. What was built (all working and tested)

**Scientific core** (`packages/irrivise_core/irrivise_core/`)
- `simulation/`: FAO-56 root-zone water balance with mass-balance checks; hidden reference farm with random soil parameters; budgeted noisy sensor (dropout, bias, stuck and delay faults); climatology + persistence forecasts built only from past data.
- `twin/`: 20-member ensemble digital twin with Kalman correction, outlier gate and sensor-offset (bias) estimation (`scenario.twin_bias`, METHODOLOGY §5.1).
- `carat/`: lookahead action values, estimated regret, value of information, budget shadow price, risk manager (hard limits + soft stress/waste layer).
- `envs/`, `agents/`: Gymnasium environment; Stable-Baselines3 PPO with presets, validation-based checkpoint selection and hash-verified loading.
- `baselines/`, `evaluation/`: baselines B0–B5, ablations A5/A6, matched experiments, paired bootstrap CIs, generated "What did the data show?" text.
- `crops/`, `data/`: AquaCrop-OSPy schedule evaluation; NASA POWER download with FAO-56 ET₀; CSV import with validation; deterministic 20-year synthetic weather (2004–2023).

**Backend** (`services/api/irrivise_api/`): FastAPI `/api/v1` (docs at `/docs`), SQLite + SQLAlchemy 2 + Alembic, separate worker process (cancellation, crash recovery, heartbeats), live progress via server-sent events, verified exports (ZIP/CSV/JSON/printable HTML). The Supabase login and Groq LLM analyst from the old prototype were removed: the spec requires no paid services, no mandatory auth and no commercial LLM.

**Frontend** (`apps/web/`): React + TypeScript + Vite + Tailwind + Radix. 11 pages: Command Center, Projects & Fields, Weather & Data Studio, Digital Twin Studio, Irrigation Simulator, Model Training Lab, CARAT Decision Lab, Experiment Benchmark, Insights & Analytics, Report & Export Center, Settings & Help. Responsive, dark mode, keyboard accessible, onboarding flow.

**Docs:** `README.md`, `ARCHITECTURE.md`, `METHODOLOGY.md` (all formulas), `REPRODUCIBILITY.md`, `IMPLEMENTATION_STATUS.md`. Results in `docs/results/`.

## 4. How to run

Needs Python 3.12 and Node 20+. No API keys or paid services.

```bash
./scripts/setup.sh
```

```bash
./scripts/dev.sh
```

Open http://127.0.0.1:5173 and choose **Explore sample field**. API docs: http://127.0.0.1:8000/docs.

Checks:

```bash
./scripts/smoke_test.sh
```

```bash
cd apps/web && npx playwright test
```

## 5. Verification (last run)

| Check | Result |
|---|---|
| Python tests (`pytest`) | 71 passed |
| Frontend lint / typecheck / build | clean |
| Frontend unit tests (Vitest) | 22 passed |
| Playwright end-to-end | 3 passed (full 10-step journey, mobile, keyboard) |
| Worker cancel / crash recovery | verified on the live system |
| CLI re-run of main benchmark | reproduced every saved number exactly (before bias handling; use `--twin-bias none` now) |
| 2026-10-29 bias-handling session | 47 core tests passed (torch/SB3/FastAPI unavailable, so RL, data-download, API and frontend tests were not run) |

## 6. Results so far (simulated farm, synthetic weather)

Setup: PPO standard preset (150k steps × 3 seeds). Best model seed 44, model id `5254f0b2-5a85-423f-9c99-aa81d0b74120`, validation reward 4.012. CARAT reading cost and B5 threshold were tuned on validation seasons 2016–2019 only (cost 0.0, threshold 0.06). Evaluation on held-out test seasons 2020–2023 × 5 seeds, budget 10 readings per season.

| Method | Water (mm) | Yield proxy (t/ha) | Readings |
|---|---|---|---|
| Fixed schedule | 350 | 8.51 | 0 |
| Soil-moisture threshold | 191 | 8.64 | 10 |
| PPO, no readings | 169 | 8.21 | 0 |
| PPO + fixed-interval readings | 181 | 8.39 | 10 |
| **Full CARAT** | 177 | 8.50 | 5.9 |
| CARAT planner (no PPO) | 188 | 8.72 | 5.9 |

- **For CARAT:** against matched-budget fixed-interval and random readings with the same PPO model, CARAT scored higher reward using about 4 fewer readings (CI excludes 0). Yield differences were inconclusive. In the budget × noise sweep it scored higher reward in all 12 settings (significant in 7).
- **Against CARAT:**
  - The planner version without PPO beat full CARAT on yield and stress.
  - Daily readings (140 per season) did not improve PPO's yield.
  - A wet-biased sensor made correction-based methods no better than PPO without readings (recorded before bias handling).

  The PPO policy looks like the weak link.
- **Caveat:** AquaCrop (default parameters) gave 14.7–14.8 t/ha for every method, so it doesn't yet discriminate between methods.

### Sensor-bias handling (added 2026-10-29)

The twin now estimates a sensor offset alongside soil water (default `twin_bias.method: augmented`; an innovation-sequence CUSUM monitor is the alternative; `none` reproduces earlier runs exactly). PPO could not be installed in that session, so it was evaluated with the planners that need no model, on test seasons × 5 seeds:

| Fault | Planner | Yield proxy, none → augmented (t/ha) |
|---|---|---|
| +0.03 wet bias | CARAT planner | 7.99 → **8.52** (+0.53, CI excludes 0) |
| +0.03 wet bias | Soil threshold | 7.86 → **8.41** (+0.55, CI excludes 0) |
| stuck | Soil threshold | 7.95 → **8.38** (+0.43, CI excludes 0) |
| healthy sensor | CARAT planner | 8.72 → 8.67 (inconclusive) |

Cost: with a healthy sensor the twin RMSE rises 11.7 → 14.3 mm, because part of the twin's own systematic error is blamed on the sensor. Full tables: `docs/results/sensor_bias_nonppo_test.md`; tuning (validation only): `docs/results/sensor_bias_tuning.json`.

Full tables: `docs/results/main_benchmark.md`, `docs/results/robustness_breakdown.md`, `docs/results/sensor_faults.md`.

## 7. Known issues / open work (priority order)

1. **Re-run the PPO sensor-fault experiment with bias handling:** retrain PPO, then `./scripts/run_sensor_faults.sh --model-id <id>`. Compare with `docs/results/sensor_faults.md` (biased: Full CARAT 8.07 t/ha vs 8.05 for PPO without readings). Then re-run the main benchmark and robustness sweep with the new default, and run `./scripts/smoke_test.sh` and Playwright (not run in the bias-handling session).
2. **Healthy-sensor cost of bias handling:** try enabling offset estimation only after the innovation monitor fires, or reduce the twin's own systematic drift, so a healthy sensor is not partly blamed.
3. **NASA POWER live download** is untested against the real service. Try one real download and simulate on it.
4. Calibrate AquaCrop against the fast simulator (or the reverse) so AquaCrop yields can tell methods apart.
5. Run the research PPO preset (500k × 5 seeds) and try training PPO with CARAT readings in the loop.
6. Not done: storage quotas are reported but not enforced; no login for non-local use; Windows scripts untested; no automated accessibility audit.

## 8. Short version to paste into a new chat

> We're building IrriVise (repo TecqHarishKrish/IrriVise, branch `claude/irrivise-end-to-end-t9d73t`), a local web platform for CARAT: PPO irrigation + digital twin + value-of-information soil readings + risk manager, on a simulated farm. Done: scientific core, FastAPI backend with worker, 11-page React UI, PPO trained, benchmarks run. CARAT beat matched-budget reading baselines on reward with fewer readings; the planner without PPO did better. On 2026-10-29 sensor-bias handling was added to the twin (augmented soil + sensor-offset state, default; CUSUM monitor alternative): with PPO-free planners it recovered most of the wet-bias yield loss (+0.53 t/ha) at a small healthy-sensor cost. PPO checkpoints are not in git. Next: retrain PPO and re-run the sensor-fault experiment (`./scripts/run_sensor_faults.sh`), then the main benchmark, then run the full test suite. Read HANDOFF.md, IMPLEMENTATION_STATUS.md and METHODOLOGY.md §5.1 first.
