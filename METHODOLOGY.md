# IrriVise methodology

IrriVise studies **CARAT — Counterfactual Action-Regret and Adaptive Twin Correction**, a method *proposed by this project*. It is not an established, validated algorithm. Everything below runs on a **simulated** farm; no result produced by this repository is a field measurement or a field validation.

Code references are given as `module:function` under `packages/irrivise_core/irrivise_core/`.

---

## 1. Components and information boundaries

| Component | Code | Knows | Never sees |
|---|---|---|---|
| Reference farm (hidden truth) | `simulation/reference_farm.py` | its own soil parameters (a random draw), realized weather, applied irrigation | — |
| Sensor gateway | `simulation/sensor.py` | the farm's current (or delayed) root-zone θ, only when asked | — |
| Estimated digital twin | `twin/ensemble.py` | the soil-parameter *prior*, observed past weather, applied irrigation, accepted readings | farm parameters, farm state |
| Forecaster | `simulation/forecast.py` | training-season climatology, observations before the decision day | the season being decided |
| Policy (PPO / baselines) | `agents/ppo.py`, `baselines/policies.py` | `AgentView` (twin summary, forecast, past observed weather, budgets) | farm, future weather |
| CARAT engine | `carat/engine.py`, `carat/lookahead.py` | twin ensemble copy, forecast, budgets | farm, future weather |
| Risk manager | `carat/risk.py` | twin ensemble copy, 1-day forecast, limits | farm |
| Evaluator | `evaluation/metrics.py` | everything — **after** the season | — |

The episode loop (`evaluation/runner.py:run_episode`) is the only place that holds both the farm and the twin. The farm's state is reachable only through `SensorGateway.measure` (budgeted) and `FieldWorld.evaluation_record()` (raises before the season ends). Separate random streams are derived from `(world seed, season)` for farm, twin, gauge error, sensor and observation policy (`util/repro.py:rng`), so all methods in an experiment face identical hidden truth (common random numbers).

**Isolation tests** (`packages/irrivise_core/tests/test_episode.py`):
* changing *only* the hidden farm's soil parameters, with no readings, leaves every decision and twin estimate bit-identical while the truth trace changes;
* changing realized rain after day 80 leaves days 1–80 bit-identical;
* operational traces contain no `true_*`/reference fields; the API's `/daily` and `/decisions` endpoints never read `evaluation_truth.csv`.

## 2. Daily execution order

1. Forecast for days *t … t+H−1* from training-season climatology and observations of days *< t*.
2. Policy proposes an *initial* action from the twin belief.
3. CARAT assesses regret (all methods, as a diagnostic) and VOI (only when the observation policy needs it).
4. Observation policy decides; a reading is requested through the gateway (budget charged once per successful reading).
5. If the reading is accepted and correction is enabled, the twin is corrected and the policy proposes again.
6. Risk manager projects the proposal (hard limits always; soft layer per method).
7. The approved depth reaches the hidden farm, which advances with **realized** weather.
8. The day's weather is revealed to the agent **with gauge/gridded error** (multiplicative lognormal, σ = 0.15 by default) and the twin propagates with it.

## 3. Water balance (fast surrogate)

`simulation/water_balance.py:step` — single-layer root zone, FAO-56 single crop coefficient approach, all depths in mm:

```
S' = S + E_root + P + I − RO − ETa − DP              (residual logged; |residual| ≤ 1e−6 mm or the step raises)
E_root = (Zr' − Zr) · 1000 · θ_sub                   water in soil newly reached by roots
RO     = SCS-CN(P) + max(0, S − θ_sat·Zr·1000)        curve-number runoff + saturation excess
Dr     = max(0, θ_fc·Zr·1000 − S),  TAW = (θ_fc − θ_wp)·Zr·1000,  RAW = p·TAW
Ks     = clip((TAW − Dr) / ((1 − p)·TAW), 0, 1)      FAO-56 eq. 84
ETa    = min(Ks · Kc(t) · ET0 · m_ET, S − θ_wp·Zr·1000)
DP     = τ · max(0, S − θ_fc·Zr·1000)                drainage above field capacity
```

* Crop: FAO-56 maize, stages 25/40/45/30 d, Kc 0.30/1.20/0.35, root depth 0.30 → 1.00 m over initial+development, p = 0.55 (`configs/crops/maize.yaml`).
* Soils: sandy loam (default), loam, clay loam (`configs/soils/*.yaml`), values inside FAO-56 Table 19 ranges; τ from AquaCrop's τ = 0.0866·Ksat^0.35; CN from USDA TR-55.
* The hidden farm draws θ_wp, θ_fc, θ_sat, τ, CN, an ET multiplier and the initial wetness from the scenario prior (`reference_farm.py:draw_soil_parameters`), and adds daily multiplicative ET process noise (σ = 0.10).
* **This surrogate is not calibrated** against AquaCrop or field data.

**Stress and yield proxy.** Daily stress is `1 − Ks`. The terminal yield **proxy** uses the FAO-33 multiplicative stage response:

```
Ya/Ym = Π_stage [1 − Ky_s · (1 − ΣETa_s / ΣETc_s)],  clipped to [0, 1];   yield_proxy = Ya/Ym · 9 t/ha
```

with Ky = 0.4/0.4/1.5/0.5 (FAO-33 vegetative/flowering/yield-formation values mapped onto the four FAO-56 stages — an approximation). It is labelled "yield proxy" everywhere and is never presented as measured or AquaCrop yield.

## 4. AquaCrop-OSPy evaluation

`crops/aquacrop_adapter.py:evaluate_schedule` replays the **applied** daily schedule of a finished run in AquaCrop-OSPy 3.1.0 (`IrrigationManagement(irrigation_method=3, Schedule=…)`, default `Crop("Maize")`, `Soil("SandyLoam")`, initial water content at FC, 200-day weather window). Decisions are not re-made inside AquaCrop; interactive step-wise injection was not used because mid-run schedule edits are not a documented, tested API. Tested API signature: `AquaCropModel(sim_start_time, sim_end_time, weather_df, soil, crop, initial_water_content, irrigation_management, …)`.

**Known model mismatch.** AquaCrop's default maize (GDD calendar, deeper rooting, harvest ≈ day 132 here) and default soil profile differ from the surrogate. Example (season 2010, synthetic weather): AquaCrop rainfed dry yield 11.3 t/ha while the surrogate's rainfed proxy collapses. AquaCrop yields therefore answer "what would AquaCrop simulate for this schedule", not "how good was the decision under the surrogate". Twin correction cannot remove this structural error.

## 5. Estimated digital twin

`twin/ensemble.py:EnsembleTwin` keeps K = 20 members, each with its own plausible soil parameters (drawn from the same prior as the farm), initial wetness and storage, equal weights. Members propagate with observed past weather plus daily multiplicative ET noise, so the ensemble spread grows between readings.

**Correction** (CARAT step 6) — 1-D Kalman update in storage units (mm), applied as a deterministic square-root ensemble shift so the ensemble mean and variance equal the formulas exactly:

```
z_mm = θ_measured · Zr · 1000,   R = (σ_sensor · Zr · 1000)² · inflation
K = P / (P + R)
mean' = mean + K (z − mean)
P' = (1 − K) P,     member_k' = mean' + √(1 − K) · (member_k − mean)
```

* P < 1e−12 mm² is treated as 0; P + R = 0 ⇒ K = 0 (no update).
* Members are clipped to [θ_wp, θ_sat]; the clip count is reported.
* Innovation gate: readings with |z − mean| > 4·√(P + R) are rejected and flagged (budget already charged).
* Delayed readings (state from *d* days earlier) inflate R by (1 + d).

## 6. Sensor gateway

`simulation/sensor.py:SensorGateway`: `z = θ_true + ε`, ε ~ N(0, σ²) with σ ∈ {0.01, 0.02, 0.04} m³/m³ in experiments. Modes: `nominal`, `missing` (dropout probability; failed attempts not charged unless `charge_failed_attempts`), `biased` (+0.03 m³/m³), `stuck` (constant after a day), `delayed` (state from *d* days earlier). Implausible values (outside [0, 0.8]) are rejected. Every attempt is recorded.

## 7. CARAT

### 7.1 Action values (`carat/lookahead.py:action_values`)

For every plausible member *k* and feasible action *a* ∈ {0, 5, 10, 15, 20} mm (projected onto the daily cap and remaining water):

```
Q̂(s_k, a) = Σ_{h=0}^{H−1} γ^h r_h − γ^H · w_T · max(0, Dr_H − RAW_H) / TAW_H
r_h = −λ_w · I_h / 20 − λ_s · (Ky_h / mean Ky) · (1 − Ks_h)
```

* H = 5 days, γ = 0.97, w_T = 0.5 (`configs/carat/default.yaml`).
* Day h = 0 applies *a*; h ≥ 1 follows a documented rollout policy (refill when depletion exceeds RAW, rounded up to the action grid, within budget).
* All lead days use the **forecast**, identical for every member and action, so values are comparable.
* The terminal term is a crude bootstrap, **not** the PPO critic.

### 7.2 Estimated regret

```
a_b  = argmax_a Σ_k w_k Q̂(s_k, a)            belief action
a*_k = argmax_a Q̂(s_k, a)                     state-informed action
R_before = Σ_k w_k [Q̂(s_k, a*_k) − Q̂(s_k, a_b)] ≥ 0
```

This is an **estimate under the twin's own model**. It is not the regret that knowledge of the hidden state would give (which would need the farm's true parameters and realized weather). Negative values beyond 1e−9 raise an error. The regret of the policy's own action is logged separately.

### 7.3 Value of information (preposterior analysis)

M = 16 seeded hypothetical readings: pick member *k* by weight, add sensor noise. For each *z*:

* `reweight` (default): posterior weights w_k(z) ∝ w_k · N(z; s_k, R); the preferred action is recomputed on the reweighted belief; remaining regret R_after(z) = Σ_k w_k(z)[Q̂(s_k, a*_k) − Q̂(s_k, a_z)].
* `kalman`: the same Kalman shift as the real correction is applied to a copy and Q̂ is recomputed.

```
GrossVOI = R_before − mean_z R_after(z)
NetVOI   = GrossVOI − c_obs − shadow_t
shadow_t = base_price · min(10, (B / L) / (remaining / days_left))     scarcity of readings vs plan
```

c_obs = 0.03 and base_price = 0.02 reward units (10 mm of irrigation = 0.1 units). Observe iff NetVOI > threshold (0), a reading remains and the gateway is available. If every member prefers the same action and R_before ≤ 1e−9, the reading is skipped without sampling ("high uncertainty alone does not trigger a reading" — tested in `test_carat.py`).

### 7.4 Risk manager (`carat/risk.py`)

* **Hard** (always): `applied = min(max(0, proposed), daily_max, remaining_water)`; delta and status logged.
* **Soft** (configurable, off in ablation A5): from the twin ensemble and the 1-day forecast, P(stress tomorrow) and expected drainage+runoff loss per candidate.
  * Stress-sensitive stage (Ky ≥ 1.0) and P(stress) > 0.5 ⇒ raise to the smallest feasible depth meeting the target, else apply the largest feasible depth and flag `unmet_stress_risk`.
  * Otherwise, if > 60 % of the irrigation is expected to be lost ⇒ reduce to the largest smaller depth whose stress probability is no worse.
* Hard constraints are the only guarantees; soft outputs are reported as uncertain estimates (quantiles of predicted 1 − Ks).

### 7.5 Decision trace

Each day stores: initial belief, forecast, initial action, candidate values and P(best), estimated regret, hypothetical regret draws, gross/net VOI, cost, shadow price, observe decision and reason, measurement, correction diagnostics, corrected belief and post-correction assessment, proposal, risk decision and remaining budgets (`decisions.json`). The CARAT Decision Lab and its plain-language explanation are built only from these fields.

## 8. Reinforcement learning

* `envs/irrigation_env.py:IrrigationEnv`: one episode = one 140-day season; `Discrete(5)` → [0, 5, 10, 15, 20] mm; `Box(0, 1, (16,))` observation (`envs/features.py`, spec `irrivise-obs-v1`) built only from the `AgentView` and normalised by **fixed physical ranges** (no data-fitted statistics, so no validation/test leakage).
* Reward per day: `−0.2·I/20 − 1.0·(Ky/mean Ky)(1 − Ks) − 2.0·max(0, proposed − applied)/20`; terminal `+5.0 · Ya/Ym`. Observation cost is not charged to PPO (PPO does not control readings); it enters the experiment-level objective `objective_with_observation_cost = Σr − 0.1 · readings`.
* Hard budget enforcement by projection inside the environment (penalties alone are not relied upon).
* Training regime: random seasons from the **training split**, domain randomisation (seasonal budget × U(0.5, 1.5), reading budget U{0..40}, sensor σ ∈ {0.01, 0.02, 0.04}, initial wetness U(0.4, 0.95)), readings at random days so the policy sees fresh and stale beliefs.
* SB3 PPO, `MlpPolicy [64, 64]`, lr 3e−4, n_steps 1024, batch 64, 10 epochs, γ 0.99, λ 0.95, clip 0.2, ent 0.01, CPU. Deterministic evaluation on **validation** seasons every `eval_freq_steps`; the best-validation checkpoint is kept; optional early stopping; non-finite parameters halt training; wall-time cap; cooperative cancellation.
* Multi-seed jobs select the seed with the highest validation reward. **Test seasons are never used for training, tuning or selection** (`test_seasons_used: []` in every manifest).
* Checkpoints are loaded only from `artifacts/models` after verifying SHA-256 and the feature-spec version.

## 9. Baselines and ablations (`baselines/policies.py:METHODS`)

| Code | Method | Irrigation | Readings | Correction | Soft risk |
|---|---|---|---|---|---|
| B0 | Fixed schedule | 10 mm every 3 d | none | – | – |
| B1 | Soil-moisture threshold | refill when est. Dr ≥ RAW | fixed interval (budget-matched) | yes | – |
| B2 | Standard PPO | PPO | none | – | – |
| B3 | PPO + fixed interval | PPO | every L/B days | yes | – |
| B4 | PPO + random | PPO | Bernoulli(B/L), seeded | yes | – |
| B5 | PPO + uncertainty threshold | PPO | std/TAW > 0.08 | yes | – |
| A5 | PPO + CARAT, no soft risk | PPO | CARAT VOI | yes | off |
| A6 | PPO + CARAT, no correction | PPO | CARAT VOI (charged, discarded) | **no** | on |
| P | Full CARAT | PPO | CARAT VOI | yes | on |
| P-noPPO | CARAT planner | belief-optimal lookahead action | CARAT VOI | yes | on |
| R-daily | PPO + daily readings | PPO | daily (**not budget-matched**, upper-information reference) | yes | – |

Hard limits apply to every method. B1's threshold uses only the twin estimate (corrected by its readings).

## 10. Evaluation protocol

* Data: whole growing seasons (planting 06-15, 140 days), **chronological** 60/20/20 split (`data/weather.py:chronological_split`); with < 3 seasons a documented reduced rule applies and evaluation never silently falls back to training seasons.
* Matched cells: (season × seed × observation budget × sensor noise), identical across methods.
* Metrics (`evaluation/metrics.py`) are recomputed from saved traces: seasonal irrigation, water savings vs reference (undefined when reference irrigation is 0), yield proxy, AquaCrop yield (optional), irrigation and total water productivity (proxy; 1 mm·ha = 10 m³), Σ(1 − Ks), stage-weighted stress, stress days, reading count/use rate, twin RMSE (mm and m³/m³) and bias, estimated regret, gross/net VOI, decision disagreement, runtime, reward, objective, and hard-constraint violation counts (must be 0).
* Statistics (`evaluation/stats.py`): mean paired difference, seeded percentile bootstrap 95 % CI (4000 resamples), Wilcoxon signed-rank p when ≥ 6 non-zero pairs; < 5 pairs is flagged "insufficient sample". "Better/worse" is claimed only when the CI excludes 0.
* Tuning (CARAT cost/threshold, B5 threshold) is done on **validation** seasons only.

## 11. Weather data

* **Synthetic fixture** (`data/synthetic.py`, seed 42): 2004–2023 daily, Markov-chain rain occurrence with monthly probabilities, gamma amounts with a lognormal year factor, harmonic temperatures with AR(1) noise, Hargreaves ET0 (FAO-56 eq. 52) at 10.79° N. Labelled *synthetic demonstration* everywhere. SHA-256 is pinned in `data/manifests/synthetic_weather_tn_v1.json` and re-verified by `scripts/sample_data.py --check`.
* **NASA POWER** (`data/nasa_power.py`): daily point API, AG community, parameters T2M_MAX, T2M_MIN, PRECTOTCORR, ALLSKY_SFC_SW_DWN, WS2M, RH2M with unit checks; FAO-56 Penman–Monteith ET0 (G = 0, RHmean approximation for e_a, POWER elevation); explicit `LST`/`UTC` time standard (not civil time); bounded retries (3, exponential backoff) for network errors, 429 and 5xx; query-keyed cache; fill values → NaN → quarantined (never imputed).
* **Forecasts** (`simulation/forecast.py`): per-day-of-season climatology (±10-day window) of training seasons for rain (expected amount) and ET0, blended with ET0 persistence of the last 3 observed days (weight 0.7^(lead+1)). Without training climatology: past-only persistence, confidence "low". Realized future weather is never copied into a forecast.

## 12. Limitations

1. Simulated farm only; the surrogate is uncalibrated and single-layer.
2. Forecast skill is limited to climatology/persistence; real numerical forecasts are not modelled.
3. Regret and VOI are model-based estimates with a short lookahead and a heuristic rollout policy; their usefulness is exactly what the experiments test.
4. A single PPO checkpoint is shared across observation policies; PPO was not trained jointly with CARAT readings.
5. AquaCrop evaluation uses default, uncalibrated crop/soil parameters and reveals structural mismatch with the surrogate.
6. Results on the synthetic fixture say nothing about real Tamil Nadu farms.
