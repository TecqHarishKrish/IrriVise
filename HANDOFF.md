# IrriVise / CARAT — handover document

_Last updated: 2026-10-29. Use this to continue the work in a new chat or by hand._

## 1. Project in one paragraph

**IrriVise — Think Before You Water** is a local web platform for researching **CARAT** (Counterfactual Action-Regret and Adaptive Twin Correction), an irrigation decision method proposed by this project. A PPO reinforcement-learning policy decides daily irrigation (0/5/10/15/20 mm) from an uncertain **digital twin** of the soil (20 plausible states). Each day CARAT estimates how much could be lost by deciding without knowing the true soil state (estimated regret) and how much a soil-moisture reading would reduce that loss (value of information). It takes a reading only when that value exceeds its cost, corrects the twin with a Kalman update, and a risk manager enforces the daily and seasonal water limits. Everything runs on a **simulated** farm. Results are not field measurements.

Repository: https://github.com/TecqHarishKrish/IrriVise

## 2. Where the code is (important)

| Item | State |
|---|---|
| Branch | `claude/irrivise-end-to-end-t9d73t`, **6 commits** on top of `main` @ `3e5ecf4` |
| On GitHub? | **No.** Every push returned HTTP 403: the Claude GitHub App has no write access to the repo (reading works). |
| Copy you have | `irrivise-end-to-end.bundle` (git bundle containing all 6 commits) |

Commits (oldest first):
1. `7445de6` Rebuild IrriVise as an end-to-end CARAT research platform
2. `4f3c9c8` Add frontend tests, E2E journey, CLI integration tests, validation tuning and docs
3. `6d1327e` Fix daily-reading reference budget and narrative semantics; add results
4. `f8e8ab8` Add reproducibility record, implementation status, CLI model-root and AquaCrop options
5. `d29e995` Correct recorded Python version; ignore TypeScript build info
6. Add handover document (this file)

### Get it onto GitHub — option A: push the bundle yourself
Run inside your local clone of IrriVise, with the bundle file in that folder:

```bash
git fetch origin main
```

```bash
git fetch ./irrivise-end-to-end.bundle claude/irrivise-end-to-end-t9d73t:claude/irrivise-end-to-end-t9d73t
```

```bash
git push -u origin claude/irrivise-end-to-end-t9d73t
```

Then open a pull request into `main` on GitHub, or merge directly (it fast-forwards): `git checkout main && git merge claude/irrivise-end-to-end-t9d73t && git push`.

### Option B: let Claude push
1. Install the Claude GitHub App on `IrriVise` with **Contents: Read and write**: https://github.com/apps/claude/installations/select_target
2. Reconnect GitHub in Claude: https://claude.ai/customize/connectors?auth_start=github&auth_start_force=1
3. Ask Claude to push the branch.

## 3. What was built (all working and tested)

**Scientific core** (`packages/irrivise_core/irrivise_core/`)
- `simulation/`: FAO-56 root-zone water balance with mass-balance checks; hidden reference farm with random soil parameters; budgeted noisy sensor (dropout, bias, stuck and delay faults); climatology + persistence forecasts built only from past data.
- `twin/`: 20-member ensemble digital twin with Kalman correction and outlier gate.
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
| CLI re-run of main benchmark | reproduced every saved number exactly |

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
  - A wet-biased sensor made correction-based methods no better than PPO without readings.

  The PPO policy looks like the weak link.
- **Caveat:** AquaCrop (default parameters) gave 14.7–14.8 t/ha for every method, so it doesn't yet discriminate between methods.

Full tables: `docs/results/main_benchmark.md`, `docs/results/robustness_breakdown.md`, `docs/results/sensor_faults.md`.

## 7. Known issues / open work (priority order)

1. **Push the branch** (section 2).
2. **Sensor-bias detection** in the twin: monitor the innovation sequence and down-weight or reject persistently biased readings. Then re-run the sensor-fault experiment.
3. **NASA POWER live download** is untested against the real service (blocked in the build sandbox; tested only with recorded responses). Try one real download and simulate on it.
4. Calibrate AquaCrop against the fast simulator (or the reverse) so AquaCrop yields can tell methods apart.
5. Run the research PPO preset (500k × 5 seeds) and try training PPO with CARAT readings in the loop.
6. Not done: storage quotas are reported but not enforced; no login for non-local use; Windows scripts untested; no automated accessibility audit.

## 8. Short version to paste into a new chat

> We're building IrriVise (repo TecqHarishKrish/IrriVise), a local web platform for CARAT: PPO irrigation + digital twin + value-of-information soil readings + risk manager, on a simulated farm. Done: full scientific core, FastAPI backend with worker, 11-page React UI, 71+22+3 passing tests, PPO trained, benchmarks run (CARAT beat matched-budget reading baselines on reward with fewer readings; the planner without PPO did better; a biased sensor hurts). The code is on branch `claude/irrivise-end-to-end-t9d73t` (6 commits) in the attached git bundle; it isn't on GitHub yet because the Claude app lacks write access. Next: push the branch, then add sensor-bias detection and re-run the sensor-fault experiment.
