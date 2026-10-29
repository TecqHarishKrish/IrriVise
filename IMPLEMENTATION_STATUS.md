# Implementation status — 2026-10-29

Status values: **DONE** (implemented and verified by the commands below), **PARTIAL** (works, with stated gaps), **BLOCKED** (could not be done in this environment).

## Starting point (audit)

The repository previously held a compact prototype: a 147-line single-file React UI, raw-`sqlite3` storage with ad-hoc column migrations, a single-process worker, a fixed-root water balance, a one-step CARAT decision, a 7-feature PPO environment, an AquaCrop schedule adapter and a NASA POWER parser. It also **required Supabase login** and shipped a **Groq (commercial LLM) analyst**, both conflicting with the specification (no mandatory auth provider, no commercial LLM, no paid/cloud services). There were no SQLAlchemy/Alembic, SSE, experiments, season splits, risk manager or PPO↔CARAT linkage.

Kept and extended: FAO-56 Penman–Monteith ETo and the NASA POWER parsing approach, the AquaCrop schedule-replay design, the hidden-reference / twin separation idea, the crop/soil defaults direction and the visual palette. Replaced: storage, worker, UI shell, science modules. Removed: Supabase auth and the Groq analyst (local single-user mode instead; deterministic, trace-generated explanations instead of an LLM).

## Environment

Linux x86-64, 4 vCPU, 15 GB RAM, Python 3.12.3 (venv), Node 22.22 / npm 10.9. PyPI and npm reachable; **NASA POWER and download.pytorch.org blocked by the sandbox egress policy**; **`git push` to GitHub refused (403: Claude GitHub App has no access to the repository)**. (The branch was later pushed to GitHub.) Bias-handling session, 2026-10-29: 2 vCPU, Python 3.13 with numpy 2.5 / pandas 3.0 / pydantic 2.13 preinstalled; PyPI, npm and download.pytorch.org all blocked, so PyTorch, Stable-Baselines3, FastAPI and the frontend toolchain were unavailable.

## Phases

| Phase | Status | Evidence / gaps |
|---|---|---|
| 0 Audit & scaffolding | DONE | Monorepo layout (`apps/web`, `services/api`, `packages/irrivise_core`, `configs`, `scripts`, `docs/results`); pinned `requirements.txt`, npm lockfile; `setup.sh`, `dev.sh` (port checks, clean shutdown), `smoke_test.sh`, `e2e_stack.sh`, Makefile. `.ps1` scripts written but **not tested** (no Windows). |
| 1 Design system & routes | DONE | 11 routes + 404; collapsible sidebar, breadcrumbs, project/scenario selector, theme toggle, mobile drawer, onboarding, skip link, provenance badges, glossary tooltips, chart table/CSV/SVG alternatives. Vitest route tests (13); Playwright mobile (390 px), keyboard and theme tests; no horizontal overflow at 390/768 px on checked pages. No automated axe/WCAG audit was run. |
| 2 Persistence & APIs | DONE | SQLAlchemy 2 models, Alembic `0001` auto-applied on API/worker start, `/api/v1` routes with error schema and OpenAPI; CRUD survives engine restart (test). |
| 3 Data & crop simulator | PARTIAL | Synthetic 20-season fixture (checksum-verified), CSV import with validation/quarantine, chronological season splits, NASA POWER downloader with cache/retries/fill-value handling (tested with mocked HTTP incl. 503 retry, offline failure, cache hit). AquaCrop-OSPy 3.1.0 full-season rainfed and scheduled runs tested. **Live NASA POWER fetch BLOCKED** (egress denied). AquaCrop default parameters are uncalibrated and differ structurally from the surrogate. |
| 4 Fast water balance | DONE | Mass-balance residual ≤ 1e−6 mm enforced; root growth, CN runoff, saturation excess, drainage; hidden farm vs twin; past-only forecasts; isolation and chronology tests. |
| 5 PPO & worker | DONE | Gymnasium env passes `check_env`; quick and standard presets trained; validation-based selection; SHA-256-verified load; tamper/incompatibility rejection; worker with spawned children, heartbeats, cancellation (verified live), SIGKILL recovery (job → interrupted, verified live), concurrency caps, SSE + polling. |
| 6 CARAT | DONE | Ensemble regret, preposterior VOI (reweight & Kalman modes), shadow price, observe/skip rule, Kalman correction with gating, risk manager (hard + soft). Tests: same-action ⇒ zero regret & skip; disagreement ⇒ positive VOI; zero budget; cost blocks; soft risk on/off; degenerate variance. |
| 6b Sensor-bias handling (2026-10-29) | PARTIAL | `twin_bias`: augmented soil + offset state (default; decoupled square-root filter) and CUSUM innovation monitor; `none` reproduces earlier runs exactly (checked row by row). 12 new/updated twin tests. Tuned on validation seasons; evaluated on test seasons with PPO-free planners (`docs/results/sensor_bias_nonppo_test.md`). **Not done:** PPO sensor-fault re-run and PPO main-benchmark re-run with the new default (PyTorch/SB3 could not be installed: package registries blocked in that session); API tests and frontend checks not run in that session. |
| 7 Simulation & replay | DONE | UI-triggered runs → saved daily/decision/truth artifacts → charts, day stepper, CARAT replay with plain explanation from trace fields, evaluation-only truth toggle. |
| 8 Experiments & ablations | DONE | Matched experiments (B0–B5, A5, A6, P, planner, daily reference), seeds, budget/noise sweeps, sensor-fault modes, paired bootstrap CIs, Wilcoxon, generated narrative with negative-result flags, failed runs listed. CLI re-run reproduces API results exactly. |
| 9 Analytics & reporting | DONE | Insights page from saved summaries, exports (ZIP/CSV/JSON/HTML with SVG charts) with hash verification and refusal on tampering (test). No server-side PNG; charts export SVG/CSV from the browser. No PDF generator (browser print). |
| 10 Hardening | PARTIAL | Upload type/size limits, path-traversal defence, idempotency + duplicate rejection, queue cap, localhost binding, CORS restricted. Not done: authentication for non-local deployment, storage quota enforcement (quota is reported, not enforced), CPU profiling, clean-machine install test. |
| 11 Research training | PARTIAL | Standard preset (150k × 3 seeds) trained and evaluated on held-out test seasons; validation-only tuning of observation parameters. Not done: research preset (500k × 5 seeds), Optuna PPO hyperparameter search (dependency installed, unused), NASA POWER historical seasons, AquaCrop-in-the-loop evaluation of all methods beyond the main benchmark. |

## Verification log (commands actually run in this session)

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | **71 passed** (56 science, 13 API/worker, 2 CLI integration) |
| `cd apps/web && npm run lint` | 0 problems |
| `npm run typecheck` | 0 errors |
| `npx vitest run` | **22 passed** |
| `npm run build` | success (Plotly in a separate lazy chunk, 1.39 MB / 474 kB gzip) |
| `npx playwright test` | **3 passed**: full 10-step offline journey, mobile nav + theme, keyboard navigation |
| `./scripts/smoke_test.sh` | passed |
| `python scripts/sample_data.py --check` | checksum match |
| Live stack (`dev.sh`): API + worker + Vite | onboarding → auto fixed run; all routes rendered with no console errors (screenshots at 1440/768/390 px) |
| Live worker: cancel a running 40k-step training | cancelled at step 1536 |
| Live worker: SIGKILL supervisor during training | job marked `interrupted`, no orphan process; restarted worker healthy |
| Standard PPO training via UI/API worker | 3 × 150k steps, ≈ 5 min/seed; selected seed 44, validation reward 4.012 |
| `scripts/tune_validation.py` | validation-only selection: CARAT obs cost 0.0, B5 threshold 0.06 |
| Main benchmark (API) + CLI re-run | 220 runs, 0 failed, 0 hard-constraint violations; CLI reproduces all means exactly |
| Robustness sweep | 576 runs, 0 failed |
| Sensor faults (missing/biased/stuck) | 3 × 48 runs, 0 failed |
| 2026-10-29, Python 3.13 + numpy 2.5 (no torch/SB3/FastAPI available): core tests excluding `test_data.py`, `test_rl_experiment.py` | **47 passed** (incl. 10 new bias tests) |
| `scripts/sensor_bias_bench.py` test + validation, `twin_bias` none/monitor/augmented | 2 × 700 runs, 0 failed; `none` matched the pre-change code on every run; nominal means matched `main_benchmark.json` (B0 8.51, B1 8.64, planner 8.72) |

## Experimental findings (simulated; synthetic weather; 4 held-out seasons)

Full numbers and caveats: [REPRODUCIBILITY.md](REPRODUCIBILITY.md#recorded-results-simulated-synthetic-weather) and `docs/results/`.

* Full CARAT used ≈ 6 of 10 readings and, against matched-budget fixed-interval and random readings with the same PPO checkpoint, achieved higher total reward excluding reading cost (CI excludes 0); yield-proxy differences were inconclusive.
* Negative results: the CARAT *planner* (lookahead action instead of PPO) beat Full CARAT on yield proxy, stress and objective; the soil-threshold baseline had lower stress; daily readings (140) did not improve PPO's yield proxy over CARAT's ≈ 6 — the PPO policy appears to be the bottleneck.
* A wet-biased sensor degraded correction-based methods to roughly no-reading PPO. Sensor-bias handling (added 2026-10-29) recovers most of that loss for the PPO-free planners (+0.53 / +0.55 t/ha, CIs exclude 0) at a small, inconclusive nominal cost; the PPO experiments have not been re-run with it yet.
* The first main-benchmark run had a bug (daily reference capped at 10 readings); it is preserved as `docs/results/main_benchmark_v1_superseded.json` and was re-run after the fix.

These are simulation results on one synthetic climate and one PPO checkpoint; they are not evidence of field performance.

## Known issues / remaining work

1. **Re-run PPO experiments with bias handling**: `./scripts/run_sensor_faults.sh` (needs a trained checkpoint; retrain with `scripts/train_ppo.py --preset cpu_standard`), then the main benchmark and robustness sweep with the new default. Compare against `docs/results/sensor_faults.md` (biased: Full CARAT 8.07 t/ha, PPO no readings 8.05).
2. NASA POWER live ingestion untested against the real service (egress blocked); verify with a real download.
3. Sensor-bias handling trades healthy-sensor accuracy (twin RMSE 11.7 → 14.3 mm) for robustness; a sensor offset and a systematic twin error are hard to separate. Options: a learned/calibrated twin (reducing its own drift), an occasional reference reading, or a gate that enables offset estimation only after the innovation monitor fires.
4. PPO is trained without CARAT in the loop and shares one checkpoint across observation policies; joint training or using the CARAT value model as a PPO critic bootstrap are open questions.
5. AquaCrop evaluation uses default parameters and shows little sensitivity to the schedules tested; calibration against the surrogate (or vice versa) is needed before AquaCrop yields can discriminate methods.
6. Storage quotas are reported but not enforced; no authentication for non-local deployment.
7. Research CPU preset and Optuna tuning not run; Windows scripts untested; no automated axe accessibility audit.

## Next priority

Re-run the PPO sensor-fault experiment, then the main benchmark, with the new default twin (`./scripts/run_sensor_faults.sh`, then `scripts/run_experiment.py --config configs/experiments/baselines.yaml`), and run the API and frontend checks (`./scripts/smoke_test.sh`), which could not run in the session that added bias handling.
