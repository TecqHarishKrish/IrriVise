# Reproducibility

## Environment used for the recorded results

| Item | Value |
|---|---|
| OS / CPU / RAM | Linux 6.18 x86-64, 4 vCPU, 15 GB (cloud container) |
| Python | 3.12.13; pins in `services/api/requirements.txt` (torch 2.5.1, stable-baselines3 2.4.1, gymnasium 1.0.0, numpy 1.26.4, pandas 2.2.3, aquacrop 3.1.0, fastapi 0.115.12, sqlalchemy 2.0.41, alembic 1.15.2) |
| Node | 22.22; exact versions in `apps/web/package.json` + `package-lock.json` |
| Code | commits `4f3c9c8` (+ the uncommitted R-daily/narrative fix later committed as `6d1327e`; manifests record `+dirty`) |
| Dataset | `data/sample/synthetic_weather_tn_v1.csv`, SHA-256 `bb092b66fb839597bcb7ec436f394e4321d3a6336ab632cd647cb9510e261195` (synthetic, seed 42) |

## Seeds and randomness

* Synthetic weather: `numpy.random.default_rng(42)`; `python scripts/sample_data.py --check` regenerates it and compares the SHA-256.
* Every simulated season derives independent streams from `(world seed, season id, purpose)` via SHA-256 (`util/repro.py:rng`) for the hidden farm, twin, gauge error, sensor, observation policy and CARAT hypothetical readings. Methods in an experiment therefore share identical hidden truth per cell.
* PPO: `stable_baselines3.common.utils.set_random_seed(seed)`, `torch.set_num_threads(1)`, CPU. SB3/PyTorch CPU training is deterministic for a fixed seed on the same platform and library versions; bit-identical results across machines are not guaranteed.
* Bootstrap CIs use a fixed seed (12345, 4000 resamples).

## Manifests

Every run, experiment and model writes a manifest with: code revision, package versions, typed scenario configuration and its SHA-256, dataset id and checksum, split rule and season ids, seeds, model checkpoint SHA-256, and SHA-256 of every artifact file. Exports refuse to proceed if an artifact no longer matches its recorded hash.

## Regenerating the recorded results

The recorded results were produced through the API/worker (UI-equivalent). The same pipeline is available from the command line.

1. Environment and checks:

```bash
./scripts/setup.sh
```

```bash
./scripts/smoke_test.sh
```

2. Train PPO (standard preset: 150 000 steps × seeds 42/43/44, validation every 10 000 steps, best checkpoint by validation reward; ≈ 5 min per seed on 4 vCPU):

```bash
.venv/bin/python scripts/train_ppo.py --preset cpu_standard --dataset sample
```

UI equivalent: Model Training Lab → *Standard CPU* → confirm. The selected model in the recorded results is seed 44 (`docs/results/model_5254f0b2-….json`, checkpoint SHA-256 `3aa651e5…2493`, validation mean reward 4.012).

3. Tune observation parameters on **validation** seasons only (2016–2019):

```bash
.venv/bin/python scripts/tune_validation.py --model-root artifacts/models --model-id <selected model id>
```

Recorded outcome (`docs/results/validation_tuning.json`): CARAT observation cost 0.0 (budget shadow price 0.02 retained), B5 uncertainty threshold 0.06.

4. Held-out benchmark on test seasons 2020–2023 (set `carat.observation_cost: 0.0` in the scenario's advanced settings, or `scenario: {carat: …}` in the YAML):

```bash
.venv/bin/python scripts/run_experiment.py --config configs/experiments/baselines.yaml --model-id <selected model id>
```

`--model-root` points at another model directory (e.g. a UI data root's `artifacts/models`); `--no-aquacrop` skips AquaCrop. **Verified:** re-running this command against the recorded checkpoint reproduced every mean in `docs/results/main_benchmark.json` (11 methods × irrigation, yield proxy, stress, readings, twin RMSE, objective) exactly — 0 mismatches.

5. Robustness sweep:

```bash
.venv/bin/python scripts/run_experiment.py --config configs/experiments/robustness.yaml --model-id <selected model id>
```

6. Render saved experiment JSON as tables:

```bash
.venv/bin/python scripts/summarize_results.py docs/results/main_benchmark.json
```

Expected outputs: `artifacts/experiments/<id or cli-timestamp>/{results.csv, summary.json, manifest.json}`; earlier outputs are never overwritten.

## Recorded results (simulated; synthetic weather)

Files: `docs/results/` — `main_benchmark.{json,md}`, `main_benchmark_report.html`, `robustness.json`, `robustness_breakdown.md`, `sensor_faults.md` (+ `fault_*.json`), `validation_tuning.json`, `model_*.json`. `main_benchmark_v1_superseded.json` is kept for transparency: in that first run the "daily readings" reference was wrongly capped at the 10-reading budget (identical to B5); it was fixed and the benchmark re-run.

### Main benchmark (test seasons 2020–2023 × seeds 1–5 = 20 matched cells per method, budget 10 readings, σ 0.02 m³/m³)

Mean [bootstrap 95% CI]; full table in `docs/results/main_benchmark.md`.

| Code | Method | Irrigation (mm) | Yield proxy (t/ha) | Σ(1−Ks) | Readings | Twin RMSE (mm) | Objective |
|---|---|---|---|---|---|---|---|
| B0 | Fixed schedule | 350.0 | 8.51 [8.06, 8.88] | 2.28 | 0 | 14.6 | −13.10 |
| B1 | Soil-moisture threshold | 190.5 | 8.64 [8.36, 8.87] | 1.45 | 10 | 10.8 | −1.55 |
| B2 | Standard PPO | 169.2 | 8.21 [7.57, 8.74] | 4.40 | 0 | 15.9 | −1.77 |
| B3 | PPO + fixed interval | 180.8 | 8.39 [7.89, 8.81] | 3.09 | 10 | 10.6 | −1.52 |
| B4 | PPO + random | 176.2 | 8.41 [7.93, 8.82] | 3.04 | 8.9 | 10.4 | −1.11 |
| B5 | PPO + uncertainty threshold | 187.5 | 8.41 [7.84, 8.88] | 3.12 | 10 | 15.1 | −1.47 |
| A5 | CARAT, no soft risk | 170.8 | 8.38 [7.89, 8.79] | 3.37 | 5.6 | 11.7 | −0.85 |
| A6 | CARAT, no correction | 181.8 | 8.37 [7.80, 8.85] | 3.62 | 8.2 | 16.4 | −1.30 |
| **P** | **Full CARAT** | 176.8 | 8.50 [8.10, 8.83] | 2.79 | 5.9 | 11.5 | 0.12 |
| P-noPPO | CARAT planner (no PPO) | 187.5 | 8.72 [8.52, 8.91] | 1.32 | 5.9 | 11.7 | 0.92 |
| R-daily | PPO + daily readings (not budget-matched) | 174.0 | 8.42 [7.94, 8.82] | 3.24 | 140 | 6.8 | −14.18 |

AquaCrop-simulated dry yields for all methods were 14.66–14.80 t/ha (AquaCrop's default deep-rooted maize is barely water-limited by these schedules; see METHODOLOGY §4).

What the paired comparisons (method − Full CARAT, 20 pairs) show:

* Against matched-budget observation baselines with the same PPO checkpoint (B3, B4), Full CARAT used ≈ 4 fewer readings and had higher total reward **excluding** reading cost (B3: −1.23 [−2.36, −0.27]; B4: −0.93 [−1.98, −0.05]); yield-proxy and irrigation differences were inconclusive. Against B5 and A6 the differences were inconclusive.
* Against PPO without readings (B2), Full CARAT had a higher yield proxy (+0.29) and less stress (CI excludes 0) at similar irrigation.
* Removing the soft risk layer (A5) saved 6 mm but lowered the yield proxy and raised stress (CIs exclude 0).
* Removing twin correction (A6) raised twin RMSE from 11.5 to 16.4 mm.
* **Negative results for the proposed PPO-based CARAT:** the CARAT *planner* (lookahead action instead of PPO) beat Full CARAT on yield proxy, stress and objective (CIs exclude 0), using 10.8 mm more water. The soil-threshold baseline B1 had lower stress (CI excludes 0) with 13.8 mm more water. Daily readings (140/season) did not improve PPO's yield proxy over CARAT's ≈ 6 readings — the PPO policy, not information, appears to be the bottleneck.

### Robustness (4 test seasons × 3 seeds per cell)

`docs/results/robustness_breakdown.md`: Full CARAT − PPO + fixed-interval readings. Total reward excluding reading cost was positive in every budget/noise cell (+0.44 to +1.45), with the CI excluding 0 in 7 of 12 cells (budgets 5–20; not at 40). CARAT used 3–9 readings where B3 used the full 5–40.

### Sensor faults (budget 10, 3 seeds)

`docs/results/sensor_faults.md`: with 25 % dropout or a stuck sensor, Full CARAT kept its yield proxy (8.47, 8.55 t/ha). With a **+0.03 m³/m³ wet bias**, both correction-based methods (B3 8.02, CARAT 8.07 t/ha) fell to roughly the no-reading PPO level (8.05): the twin trusts biased readings and under-irrigates. No bias detection is implemented.

### Caveats on these numbers

* One synthetic weather generator, four test seasons, one PPO checkpoint for all PPO methods. Cells share seasons, so bootstrap CIs over cells are optimistic about generalisation.
* Every outcome comes from the simulated reference farm and the uncalibrated surrogate; yields are proxies. None of this is evidence about real fields or NASA POWER historical seasons (not reachable from the build environment).
