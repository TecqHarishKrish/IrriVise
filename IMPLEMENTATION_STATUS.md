# Implementation status — 2026-10-14

This is a verified offline prototype. It does **not** satisfy the full master specification.

| Phase | Status | Evidence and remaining work |
|---|---|---|
| 0 — Audit/scaffold | Partial | Started from an empty folder. Python 3.12.14 and Node 24.19.0 were found through the bundled runtime. `setup.sh` passed on the populated environment; clean-machine install and Windows startup were not tested. |
| 1 — Design/routes | Partial | All eleven routes render. A browser journey verified navigation and creation at a narrow viewport. Formal accessibility and multi-viewport tests remain. |
| 2 — Persistence/API | Partial | SQLite persists projects, scenarios, durable simulation/training jobs and run metadata. Typed FastAPI routes and integration tests pass. SQLAlchemy/Alembic, complete CRUD, SSE, imports and quota controls remain. |
| 3 — Data/AquaCrop | Partial | Strict synthetic CSV validation and an actual AquaCrop-OSPy 3.1.0 full-season rainfed/scheduled-irrigation test pass. Worker evaluates completed schedules. NASA POWER, historical splits and agronomic calibration remain. |
| 4 — Fast model | Partial | Mass balance, hidden reference/twin split, past-based forecast, seeded observations and zero-budget tests pass. Root depth and forecast are simplified. |
| 5 — PPO/worker | Partial | Separate worker runs a real quick PPO job with step progress, cancellation polling, checkpoint hash, save/load and one-step inference. CLI 2,048-step smoke training and UI 256-step job succeeded. No validation selection, multi-seed training, leases or heartbeat. |
| 6 — CARAT | Partial | Plausible states, estimated regret, hypothetical readings, conditional VOI, correction and hard budgets work. No PPO connection, multi-day rollout or crop-stage risk manager. |
| 7 — Replay | Partial | Saved daily JSON, twin evaluation view, paginated CARAT trace and actual job states. No pause/step replay control. |
| 8 — Experiments | Partial | Individual fixed and CARAT runs can use the same scenario/seed/weather. Matched multi-seed benchmark, ablations and confidence intervals are absent. |
| 9 — Reports | Partial | Latest run JSON export and actual summary table. No printable report or verified chart export. |
| 10 — Hardening | Partial | `smoke_test.sh` passes; manual browser journey passes. Lint, automated Playwright, clean install, quota/security review and desktop/tablet testing remain. |
| 11 — Research training | Partial | Quick functional PPO checkpoint exists. No held-out testing, model selection or research-quality claims. |

## Verification log

- `./scripts/setup.sh` with bundled Python/Node paths: **passed** on this populated environment; pip requirements already installed and pnpm lockfile up to date.
- `./scripts/smoke_test.sh`: **12 passed, 1 Starlette deprecation warning**; TypeScript typecheck and Vite production build passed (1,635 modules transformed).
- `python scripts/train_ppo.py --preset cpu_quick --dataset sample --seed 42 --timesteps 2048`: **passed** with 2,048 actual steps, checkpoint save/load and one-step inference; no quality score was measured.
- Live localhost browser: created a project/scenario, queued fixed and CARAT simulations, observed worker completion, queued a 256-step PPO job and saw its checkpoint after success. The command center displayed AquaCrop-simulated dry yield from a saved 150-day run.
- AquaCrop integration test: rainfed and scheduled maize runs both returned finite harvest results; scheduled irrigation was positive and rainfed irrigation was zero.
- Ordinary `/daily` API excludes hidden reference storage; `/evaluation` exposes it only in post-run evaluation. The isolation is within application code, not authentication/security enforcement.

## Actual synthetic demonstration outcomes

Two 150-day runs used the same sample dataset checksum `4827ab9decbfa9fb97ea83615dc90cda0c01eb0b90aa621d14557f5824d2c783`, scenario, 350 mm budget and seed 42:

| Controller | Irrigation | AquaCrop-simulated dry yield | Simulated readings |
|---|---:|---:|---:|
| Fixed interval | 350 mm | 14.8696 t/ha | 0 |
| CARAT prototype | 320 mm | 14.8696 t/ha | 6 |

These are **one synthetic scenario and one seed**, with no held-out weather, statistical interval or field validation. The equal crop-model yield and 30 mm irrigation difference are descriptive only; they do not establish method superiority.

## Highest priority next action

Implement bounded NASA POWER historical weather ingestion and season-level train/validation/test splits, then run matched multi-seed evaluation before tuning or making performance claims.
