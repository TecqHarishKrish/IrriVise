# IrriVise architecture

```text
            Browser (React 18 + TypeScript + Vite, 11 routes)
                │  HTTP JSON  ·  SSE (/jobs/{id}/events, polling fallback)
                ▼
  FastAPI  /api/v1   (services/api/irrivise_api)          127.0.0.1:8000
  ├─ validation (Pydantic v2), error schema {code,message,details,request_id}
  ├─ SQLite metadata via SQLAlchemy 2, schema via Alembic (auto-migrated on start)
  ├─ enqueue heavy work → jobs table (never runs it in a request handler)
  └─ reads saved artifacts, verifies hashes for exports
                │  durable SQLite job queue
                ▼
  Worker supervisor  python -m irrivise_api.worker
  ├─ atomic claim (conditional UPDATE), concurrency caps (1 training, 2 other)
  ├─ one spawned child process per job, heartbeats, stale-job recovery
  ├─ cancellation: cooperative flag → terminate after grace period
  └─ children detect supervisor loss and stop (job → interrupted)
                │  imports
                ▼
  Scientific core  packages/irrivise_core/irrivise_core
  data/  crops/  simulation/  twin/  carat/  envs/  agents/  baselines/  evaluation/  config/  util/
                │
                ▼
  Files under IRRIVISE_DATA_ROOT (default: repo root)
  data/irrivise.sqlite3 · data/{sample,raw,processed,manifests} · artifacts/{runs,models,experiments,exports}
```

## Packages

| Path | Responsibility |
|---|---|
| `packages/irrivise_core/irrivise_core/config` | Typed, frozen, hashable Pydantic models; YAML loading from `configs/` |
| `…/data` | Weather validation/quarantine, season extraction, chronological splits, synthetic fixture, NASA POWER |
| `…/simulation` | Water balance, hidden reference farm, sensor gateway, forecaster, `FieldWorld` day loop |
| `…/twin` | Ensemble belief and Kalman correction |
| `…/carat` | Lookahead action values, regret/VOI engine, risk manager |
| `…/envs` | Gymnasium environment, feature vector, reward |
| `…/agents` | PPO training with validation selection, verified checkpoint loading, policy wrapper |
| `…/baselines` | Irrigation and observation policies, method registry (B0–B5, A5, A6, P) |
| `…/evaluation` | Episode runner + decision traces, metrics, paired statistics, matched experiments |
| `…/crops` | AquaCrop-OSPy schedule evaluation |
| `services/api/irrivise_api/routes` | REST endpoints (system, projects, datasets, simulations, training, experiments, jobs, exports, analytics) |
| `services/api/irrivise_api/services` | Scenario ↔ config, dataset registry, job state machine, safe artifact paths, HTML reports |
| `services/api/irrivise_api/worker` | Supervisor and job handlers |
| `apps/web/src` | `app/` shell, `pages/` (11), `components/` (design system, charts), `api/` (typed client, hooks, SSE) |

## Job lifecycle

```text
queued ──claim──▶ running ──▶ succeeded   (artifacts written + hashed, DB rows committed)
   │                 ├──────▶ failed      (exception text stored, artifacts not registered)
   │                 ├──────▶ cancelled   (cooperative flag, or terminated after grace period)
   │                 └──────▶ interrupted (heartbeat lost / supervisor died; never auto-resumed)
   └──cancel──▶ cancelled
```

Every transition is checked (`services/jobs.py:transition`) and appends a `job_events` row with a per-job increasing `sequence`, timestamp, phase, step counts and optional metric. SSE streams these rows (`id:` = sequence, resumable with `Last-Event-ID`, keep-alives every 15 s); `?format=json&after=N` is the polling fallback. Duplicate active submissions (same kind + payload) return 409; an `Idempotency-Key` header returns the original job; at most 25 active jobs.

## Data access boundaries in the API

* `/simulations/{id}/daily` and `/decisions` read `daily.csv` / `decisions.json` only (no hidden state).
* `/simulations/{id}/evaluation` is the single route that returns `evaluation_truth.csv` and hidden parameters; the UI shows it only behind an explicit "post-run evaluation" switch with a red shield label.
* `/simulations/{id}` strips hidden parameters from the manifest it returns.

## Artifacts (per run)

```
artifacts/runs/<run_id>/
  daily.csv              operational daily trace (twin, actions, readings, budgets)
  decisions.json         CARAT decision traces (with plausible states for single runs)
  evaluation_truth.csv   hidden reference trace — evaluation only
  summary.json           metrics computed from the traces
  manifest.json          config, seeds, dataset checksum, model checksum, code revision, package versions, file SHA-256s
```

Experiments write `results.csv`, `summary.json`, `manifest.json`; models write `<id>.zip` + `<id>.json`. Exports are new immutable files; download re-verifies the export hash, and export creation re-verifies the source artifact hashes.

## Security posture (local single-user)

No authentication — bind to 127.0.0.1 (scripts do). CORS limited to the local UI origins. Uploads: `.csv` only, content-type check, 5 MB cap, parsed and validated before storage, stored under generated names. All artifact paths derive from generated UUIDs and are resolved under the data root (`services/artifacts.py:safe_join`). Checkpoints are never accepted from users and are hash-verified before loading. Only the fixed NASA POWER endpoint is contacted. Names reject angle brackets; React escapes all rendered text.

## Frontend

React 18, React Router 6, TanStack Query (server state, retry rules), React Hook Form + Zod (forms), Tailwind with semantic HSL tokens and a dark theme, Radix primitives in shadcn-style components, Recharts (primary charts, each with table/CSV/SVG alternatives), Plotly.js (lazy-loaded Q̂ heatmap only), TanStack Table, Lucide icons. Active project/scenario persist per browser and are validated against the API. Tests: Vitest + Testing Library (unit), Playwright (E2E against an isolated stack started by `scripts/e2e_stack.sh`).
