> **Recorded before sensor-bias handling existed** (equivalent to `twin_bias.method: none`). The twin's default is now the augmented offset state (METHODOLOGY §5.1); its effect on PPO-free planners is in `sensor_bias_nonppo_test.md`. Re-run these PPO experiments with `./scripts/run_sensor_faults.sh` (add `--twin-bias none` to reproduce the numbers below).

## Sensor fault: missing (test seasons)

Experiment `1a889146-e293-4bcd-b8ca-0037ae44d205` · split **test** · seeds [1, 2, 3] · observation budgets [10] · sensor noise [0.02] m³/m³ (missing) · reference **ppo_fixed_interval** · 48 runs, 0 failed, 0 hard-constraint violations.

Mean [bootstrap 95% CI] over matched cells:

| Code | Method | n | Irrigation (mm) | Yield proxy (t/ha) | AquaCrop yield (t/ha) | Σ(1−Ks) | Readings | Twin RMSE (mm) | Objective |
|---|---|---|---|---|---|---|---|---|---|
| B2 | Standard PPO (no observations) | 12 | 169.6 [137.1, 200.4] | 8.05 [7.09, 8.82] | — | 5.31 [0.93, 10.96] | 0.0 [0.0, 0.0] | 15.5 [11.5, 19.7] | -2.94 [-9.83, 2.45] |
| B3 | PPO + fixed-interval readings | 12 | 181.2 [141.2, 221.2] | 8.40 [7.70, 8.96] | — | 3.05 [0.32, 6.67] | 10.0 [10.0, 10.0] | 10.5 [8.3, 12.6] | -1.38 [-6.34, 2.22] |
| A6 | PPO + CARAT readings, no twin correction | 12 | 179.2 [143.8, 212.5] | 8.22 [7.35, 8.91] | — | 4.53 [0.54, 9.81] | 7.8 [6.2, 9.3] | 15.9 [11.9, 19.8] | -2.32 [-8.38, 2.22] |
| P | Full CARAT (PPO + VOI readings + correction + risk) | 12 | 180.4 [139.2, 222.5] | 8.47 [7.85, 8.92] | — | 3.20 [0.53, 6.95] | 5.2 [4.0, 6.2] | 10.8 [8.5, 13.2] | -0.01 [-3.93, 2.70] |

Paired differences (method − ppo_fixed_interval), mean [95% CI], status:

| Method | seasonal_irrigation_mm | yield_proxy_t_ha | cumulative_stress | objective_with_observation_cost |
|---|---|---|---|---|
| ppo | -11.7 [-28.8, +6.7] — inconclusive (CI includes 0) | -0.355 [-0.638, -0.104] — worse (CI excludes 0) | +2.27 [+0.50, +4.35] — worse (CI excludes 0) | -1.553 [-3.720, +0.260] — inconclusive (CI includes 0) |
| ppo_carat_no_correction | -2.1 [-17.1, +13.8] — inconclusive (CI includes 0) | -0.183 [-0.360, -0.033] — worse (CI excludes 0) | +1.49 [+0.15, +3.18] — worse (CI excludes 0) | -0.933 [-2.187, +0.077] — inconclusive (CI includes 0) |
| carat_full | -0.8 [-6.2, +4.2] — inconclusive (CI includes 0) | +0.064 [-0.042, +0.183] — inconclusive (CI includes 0) | +0.15 [-0.16, +0.50] — inconclusive (CI includes 0) | +1.369 [+0.466, +2.466] — better (CI excludes 0) |

What the data showed (generated):

- 4 methods were run on 12 matched cell(s) each (split: test; seeds: 3). All outcomes are simulated; yields are FAO-33 proxies unless an AquaCrop column is shown. Differences are method − reference.
- Standard PPO (no observations) vs ppo_fixed_interval: irrigation -11.7 mm (inconclusive (CI includes 0)); yield proxy -0.355 t/ha (worse (CI excludes 0)); cumulative stress +2.27 (worse (CI excludes 0)); objective -1.553 (inconclusive (CI includes 0)); n = 12 pairs.
- PPO + CARAT readings, no twin correction vs ppo_fixed_interval: irrigation -2.1 mm (inconclusive (CI includes 0)); yield proxy -0.183 t/ha (worse (CI excludes 0)); cumulative stress +1.49 (worse (CI excludes 0)); objective -0.933 (inconclusive (CI includes 0)); n = 12 pairs.
- Full CARAT (PPO + VOI readings + correction + risk) vs ppo_fixed_interval: irrigation -0.8 mm (inconclusive (CI includes 0)); yield proxy +0.064 t/ha (inconclusive (CI includes 0)); cumulative stress +0.15 (inconclusive (CI includes 0)); objective +1.369 (better (CI excludes 0)); n = 12 pairs.
- These results come from a simulated reference farm and do not demonstrate field performance.

## Sensor fault: biased (test seasons)

Experiment `2d467f73-40c4-4fb1-a9be-f2556367d7a4` · split **test** · seeds [1, 2, 3] · observation budgets [10] · sensor noise [0.02] m³/m³ (biased) · reference **ppo_fixed_interval** · 48 runs, 0 failed, 0 hard-constraint violations.

Mean [bootstrap 95% CI] over matched cells:

| Code | Method | n | Irrigation (mm) | Yield proxy (t/ha) | AquaCrop yield (t/ha) | Σ(1−Ks) | Readings | Twin RMSE (mm) | Objective |
|---|---|---|---|---|---|---|---|---|---|
| B2 | Standard PPO (no observations) | 12 | 169.6 [137.1, 200.4] | 8.05 [7.09, 8.82] | — | 5.31 [0.93, 10.96] | 0.0 [0.0, 0.0] | 15.5 [11.5, 19.7] | -2.94 [-9.83, 2.45] |
| B3 | PPO + fixed-interval readings | 12 | 156.2 [118.8, 193.8] | 8.02 [7.14, 8.73] | — | 5.27 [1.44, 10.07] | 10.0 [10.0, 10.0] | 14.3 [10.5, 18.4] | -3.85 [-10.17, 1.14] |
| A6 | PPO + CARAT readings, no twin correction | 12 | 180.0 [144.6, 212.9] | 8.22 [7.34, 8.94] | — | 4.53 [0.41, 9.86] | 8.0 [6.6, 9.2] | 15.9 [11.9, 19.8] | -2.36 [-8.53, 2.28] |
| P | Full CARAT (PPO + VOI readings + correction + risk) | 12 | 150.4 [108.3, 192.5] | 8.07 [7.26, 8.71] | — | 5.16 [1.43, 9.92] | 5.2 [3.9, 6.4] | 14.5 [11.8, 17.9] | -2.69 [-8.22, 1.62] |

Paired differences (method − ppo_fixed_interval), mean [95% CI], status:

| Method | seasonal_irrigation_mm | yield_proxy_t_ha | cumulative_stress | objective_with_observation_cost |
|---|---|---|---|---|
| ppo | +13.3 [+0.0, +27.1] — inconclusive (CI includes 0) | +0.025 [-0.111, +0.155] — inconclusive (CI includes 0) | +0.05 [-0.83, +1.02] — inconclusive (CI includes 0) | +0.915 [+0.082, +1.745] — better (CI excludes 0) |
| ppo_carat_no_correction | +23.8 [+11.7, +35.8] — worse (CI excludes 0) | +0.198 [+0.076, +0.339] — better (CI excludes 0) | -0.74 [-1.58, +0.04] — inconclusive (CI includes 0) | +1.489 [+0.655, +2.457] — better (CI excludes 0) |
| carat_full | -5.8 [-12.1, +0.8] — inconclusive (CI includes 0) | +0.045 [-0.057, +0.156] — inconclusive (CI includes 0) | -0.11 [-0.46, +0.25] — inconclusive (CI includes 0) | +1.164 [+0.307, +2.243] — better (CI excludes 0) |

What the data showed (generated):

- 4 methods were run on 12 matched cell(s) each (split: test; seeds: 3). All outcomes are simulated; yields are FAO-33 proxies unless an AquaCrop column is shown. Differences are method − reference.
- Standard PPO (no observations) vs ppo_fixed_interval: irrigation +13.3 mm (inconclusive (CI includes 0)); yield proxy +0.025 t/ha (inconclusive (CI includes 0)); cumulative stress +0.05 (inconclusive (CI includes 0)); objective +0.915 (better (CI excludes 0)); n = 12 pairs.
- PPO + CARAT readings, no twin correction vs ppo_fixed_interval: irrigation +23.8 mm (worse (CI excludes 0)); yield proxy +0.198 t/ha (better (CI excludes 0)); cumulative stress -0.74 (inconclusive (CI includes 0)); objective +1.489 (better (CI excludes 0)); n = 12 pairs.
- Full CARAT (PPO + VOI readings + correction + risk) vs ppo_fixed_interval: irrigation -5.8 mm (inconclusive (CI includes 0)); yield proxy +0.045 t/ha (inconclusive (CI includes 0)); cumulative stress -0.11 (inconclusive (CI includes 0)); objective +1.164 (better (CI excludes 0)); n = 12 pairs.
- These results come from a simulated reference farm and do not demonstrate field performance.

## Sensor fault: stuck (test seasons)

Experiment `9913161e-f96e-4058-ae7d-093246492d4c` · split **test** · seeds [1, 2, 3] · observation budgets [10] · sensor noise [0.02] m³/m³ (stuck) · reference **ppo_fixed_interval** · 48 runs, 0 failed, 0 hard-constraint violations.

Mean [bootstrap 95% CI] over matched cells:

| Code | Method | n | Irrigation (mm) | Yield proxy (t/ha) | AquaCrop yield (t/ha) | Σ(1−Ks) | Readings | Twin RMSE (mm) | Objective |
|---|---|---|---|---|---|---|---|---|---|
| B2 | Standard PPO (no observations) | 12 | 169.6 [137.1, 200.4] | 8.05 [7.09, 8.82] | — | 5.31 [0.93, 10.96] | 0.0 [0.0, 0.0] | 15.5 [11.5, 19.7] | -2.94 [-9.83, 2.45] |
| B3 | PPO + fixed-interval readings | 12 | 176.7 [126.2, 228.3] | 8.32 [7.81, 8.76] | — | 3.16 [0.97, 5.95] | 10.0 [10.0, 10.0] | 14.8 [11.7, 18.0] | -1.75 [-5.11, 1.09] |
| A6 | PPO + CARAT readings, no twin correction | 12 | 180.0 [144.6, 212.9] | 8.22 [7.34, 8.94] | — | 4.53 [0.41, 9.86] | 8.0 [6.6, 9.2] | 15.9 [11.9, 19.8] | -2.36 [-8.53, 2.28] |
| P | Full CARAT (PPO + VOI readings + correction + risk) | 12 | 182.5 [132.1, 232.9] | 8.55 [8.17, 8.85] | — | 2.66 [0.67, 5.21] | 5.8 [4.7, 6.9] | 13.9 [9.7, 18.6] | 0.43 [-1.75, 2.24] |

Paired differences (method − ppo_fixed_interval), mean [95% CI], status:

| Method | seasonal_irrigation_mm | yield_proxy_t_ha | cumulative_stress | objective_with_observation_cost |
|---|---|---|---|---|
| ppo | -7.1 [-33.8, +17.5] — inconclusive (CI includes 0) | -0.275 [-0.853, +0.265] — inconclusive (CI includes 0) | +2.15 [-0.54, +5.34] — inconclusive (CI includes 0) | -1.190 [-5.603, +2.815] — inconclusive (CI includes 0) |
| ppo_carat_no_correction | +3.3 [-22.5, +27.9] — inconclusive (CI includes 0) | -0.102 [-0.598, +0.376] — inconclusive (CI includes 0) | +1.36 [-1.01, +4.22] — inconclusive (CI includes 0) | -0.616 [-4.227, +2.832] — inconclusive (CI includes 0) |
| carat_full | +5.8 [-15.8, +25.4] — inconclusive (CI includes 0) | +0.223 [-0.088, +0.541] — inconclusive (CI includes 0) | -0.50 [-1.80, +0.81] — inconclusive (CI includes 0) | +2.171 [+0.188, +4.230] — better (CI excludes 0) |

What the data showed (generated):

- 4 methods were run on 12 matched cell(s) each (split: test; seeds: 3). All outcomes are simulated; yields are FAO-33 proxies unless an AquaCrop column is shown. Differences are method − reference.
- Standard PPO (no observations) vs ppo_fixed_interval: irrigation -7.1 mm (inconclusive (CI includes 0)); yield proxy -0.275 t/ha (inconclusive (CI includes 0)); cumulative stress +2.15 (inconclusive (CI includes 0)); objective -1.190 (inconclusive (CI includes 0)); n = 12 pairs.
- PPO + CARAT readings, no twin correction vs ppo_fixed_interval: irrigation +3.3 mm (inconclusive (CI includes 0)); yield proxy -0.102 t/ha (inconclusive (CI includes 0)); cumulative stress +1.36 (inconclusive (CI includes 0)); objective -0.616 (inconclusive (CI includes 0)); n = 12 pairs.
- Full CARAT (PPO + VOI readings + correction + risk) vs ppo_fixed_interval: irrigation +5.8 mm (inconclusive (CI includes 0)); yield proxy +0.223 t/ha (inconclusive (CI includes 0)); cumulative stress -0.50 (inconclusive (CI includes 0)); objective +2.171 (better (CI excludes 0)); n = 12 pairs.
- These results come from a simulated reference farm and do not demonstrate field performance.

