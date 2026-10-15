# Prototype methodology

## Weather and time

The bundled dataset is 150 generated days starting 2025-06-01, seed 42. It is a software fixture, with no NASA POWER or field provenance. A controller sees the date, yesterday's realized rainfall, and a fixed illustrative ET₀ forecast. It does not see the current day's realized rain before acting. The fixed forecast is deliberately simple and should not be mistaken for a validated forecast model.

## Water balance

Root-zone storage is in mm: `theta (m³/m³) × root depth (m) × 1000`. The daily step adds rain and irrigation, counts overflow above saturation as runoff, limits ET by water above wilting, then drains 55% of storage above field capacity. It records a mass-balance residual for every day. Root depth remains fixed at 0.6 m. The stress proxy is `1 − relative_water_availability` before ET. The terminal "yield proxy" is `7 × max(0, 1 − mean_daily_stress)` in a t/ha scale, an arbitrary demonstration score **without AquaCrop calibration or field validation**.

## Estimated twin and CARAT prototype

The estimated state is propagated with a past-based forecast, and its variance grows while unobserved. The hidden reference uses realized weather only after irrigation is selected. A simulated measurement reads the hidden state and adds seeded Gaussian noise. Kalman-style correction uses `K=P/(P+R)`. CARAT samples 20 plausible states and 16 hypothetical sensor readings. It evaluates one-day action values with the same surrogate objective, computes expected action regret, conditional regret after hypothetical readings, and net value after a modeled observation cost. It requests a reading only when net value is positive and budget remains. Hard irrigation and observation budgets are enforced.

This is a small prototype of the proposed method. Its decisions do not use the PPO policy or critic, multi-day rollout, or a crop-stage risk manager. AquaCrop evaluates the resulting schedule afterward. Its apparent numerical performance is not research evidence.

## AquaCrop and PPO boundaries

After a controller run, the worker passes its complete irrigation schedule and the same synthetic weather to AquaCrop-OSPy 3.1.0 using its supported scheduled-irrigation interface. AquaCrop results are labeled **AquaCrop-simulated** and are separate from the fast model's uncalibrated yield proxy. The crop model may harvest before the end of the 150-day fast trace; the two outputs therefore describe different horizons and are not a calibrated validation of the fast proxy.

PPO uses a seven-feature Gymnasium observation containing only estimated soil water, uncertainty, season progress, past rain, a past-based forecast, fixed ET₀ forecast, and remaining water budget. Reward is revealed after acting on the hidden reference simulator. The quick preset trains on repeated synthetic seasons and checks checkpoint save/load/inference. There is no held-out weather season, multi-seed validation, or CARAT connection yet.
