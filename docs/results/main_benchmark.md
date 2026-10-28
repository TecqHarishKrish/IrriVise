## Main benchmark v2: baselines, ablations and CARAT (test seasons)

Experiment `6d71b46b-1e35-4c56-bc7c-fed6b1785049` · split **test** · seeds [1, 2, 3, 4, 5] · observation budgets [10] · sensor noise [0.02] m³/m³ (nominal) · reference **carat_full** · 220 runs, 0 failed, 0 hard-constraint violations.

Mean [bootstrap 95% CI] over matched cells:

| Code | Method | n | Irrigation (mm) | Yield proxy (t/ha) | AquaCrop yield (t/ha) | Σ(1−Ks) | Readings | Twin RMSE (mm) | Objective |
|---|---|---|---|---|---|---|---|---|---|
| B0 | Fixed schedule (10 mm / 3 days) | 20 | 350.0 [350.0, 350.0] | 8.51 [8.06, 8.88] | 14.80 [14.79, 14.81] | 2.28 [0.52, 4.39] | 0.0 [0.0, 0.0] | 14.6 [10.6, 19.5] | -13.10 [-15.53, -11.09] |
| B1 | Soil-moisture threshold (MAD rule) | 20 | 190.5 [151.0, 231.5] | 8.64 [8.36, 8.87] | 14.74 [14.71, 14.77] | 1.45 [0.53, 2.57] | 10.0 [10.0, 10.0] | 10.8 [8.9, 12.8] | -1.55 [-5.26, 1.36] |
| B2 | Standard PPO (no observations) | 20 | 169.2 [143.0, 194.0] | 8.21 [7.57, 8.74] | 14.70 [14.67, 14.74] | 4.40 [1.42, 8.08] | 0.0 [0.0, 0.0] | 15.9 [12.4, 19.9] | -1.77 [-6.36, 1.97] |
| B3 | PPO + fixed-interval readings | 20 | 180.8 [153.0, 209.2] | 8.39 [7.89, 8.81] | 14.71 [14.67, 14.74] | 3.09 [0.99, 5.61] | 10.0 [10.0, 10.0] | 10.6 [8.7, 12.6] | -1.52 [-4.86, 1.31] |
| B4 | PPO + random readings (matched budget) | 20 | 176.2 [147.2, 206.0] | 8.41 [7.93, 8.82] | 14.71 [14.68, 14.74] | 3.04 [0.91, 5.57] | 8.9 [8.2, 9.6] | 10.4 [8.5, 12.4] | -1.11 [-4.37, 1.61] |
| B5 | PPO + uncertainty-threshold readings | 20 | 187.5 [161.2, 211.8] | 8.41 [7.84, 8.88] | 14.71 [14.68, 14.74] | 3.12 [0.68, 6.15] | 10.0 [10.0, 10.0] | 15.1 [12.2, 18.2] | -1.47 [-5.32, 1.65] |
| A5 | PPO + CARAT readings, no soft risk layer | 20 | 170.8 [140.0, 202.2] | 8.38 [7.89, 8.79] | 14.71 [14.68, 14.74] | 3.37 [1.10, 6.09] | 5.6 [4.7, 6.5] | 11.7 [9.5, 14.0] | -0.85 [-3.99, 1.84] |
| A6 | PPO + CARAT readings, no twin correction | 20 | 181.8 [153.5, 208.0] | 8.37 [7.80, 8.85] | 14.70 [14.67, 14.73] | 3.62 [0.94, 6.98] | 8.2 [7.0, 9.1] | 16.4 [12.9, 20.5] | -1.30 [-5.28, 1.85] |
| P | Full CARAT (PPO + VOI readings + correction + risk) | 20 | 176.8 [144.2, 210.2] | 8.50 [8.10, 8.83] | 14.71 [14.68, 14.74] | 2.79 [0.89, 5.12] | 5.9 [5.0, 6.8] | 11.5 [9.3, 13.8] | 0.12 [-2.26, 2.14] |
| P-noPPO | CARAT planner (lookahead action + VOI readings + risk) | 20 | 187.5 [146.0, 231.2] | 8.72 [8.52, 8.91] | 14.66 [14.62, 14.70] | 1.32 [0.40, 2.43] | 5.9 [4.9, 6.8] | 11.7 [9.6, 14.0] | 0.92 [-0.61, 2.27] |
| R-daily | PPO + daily readings (upper-information reference) | 20 | 174.0 [143.2, 207.0] | 8.42 [7.94, 8.82] | 14.70 [14.65, 14.73] | 3.24 [1.05, 5.74] | 140.0 [140.0, 140.0] | 6.8 [6.2, 7.4] | -14.18 [-17.24, -11.52] |

Paired differences (method − carat_full), mean [95% CI], status:

| Method | seasonal_irrigation_mm | yield_proxy_t_ha | cumulative_stress | objective_with_observation_cost |
|---|---|---|---|---|
| fixed_schedule | +173.2 [+139.8, +205.8] — worse (CI excludes 0) | +0.013 [-0.174, +0.220] — inconclusive (CI includes 0) | -0.51 [-1.40, +0.29] — inconclusive (CI includes 0) | -13.221 [-14.232, -11.946] — worse (CI excludes 0) |
| soil_threshold | +13.8 [+6.0, +22.0] — worse (CI excludes 0) | +0.138 [-0.018, +0.304] — inconclusive (CI includes 0) | -1.34 [-2.71, -0.22] — better (CI excludes 0) | -1.678 [-4.231, -0.216] — worse (CI excludes 0) |
| ppo | -7.5 [-22.5, +7.0] — inconclusive (CI includes 0) | -0.291 [-0.604, -0.005] — worse (CI excludes 0) | +1.60 [+0.18, +3.17] — worse (CI excludes 0) | -1.893 [-4.482, +0.387] — inconclusive (CI includes 0) |
| ppo_fixed_interval | +4.0 [-2.8, +10.5] — inconclusive (CI includes 0) | -0.112 [-0.239, +0.000] — inconclusive (CI includes 0) | +0.30 [-0.08, +0.70] — inconclusive (CI includes 0) | -1.640 [-2.755, -0.709] — worse (CI excludes 0) |
| ppo_random | -0.5 [-6.2, +5.2] — inconclusive (CI includes 0) | -0.086 [-0.205, +0.020] — inconclusive (CI includes 0) | +0.25 [-0.11, +0.63] — inconclusive (CI includes 0) | -1.237 [-2.250, -0.381] — worse (CI excludes 0) |
| ppo_uncertainty | +10.8 [-2.5, +23.2] — inconclusive (CI includes 0) | -0.093 [-0.346, +0.146] — inconclusive (CI includes 0) | +0.33 [-0.58, +1.30] — inconclusive (CI includes 0) | -1.590 [-3.463, +0.142] — inconclusive (CI includes 0) |
| ppo_carat_no_risk | -6.0 [-10.8, -1.5] — better (CI excludes 0) | -0.123 [-0.252, -0.025] — worse (CI excludes 0) | +0.57 [+0.14, +1.16] — worse (CI excludes 0) | -0.969 [-1.885, -0.204] — worse (CI excludes 0) |
| ppo_carat_no_correction | +5.0 [-8.5, +17.8] — inconclusive (CI includes 0) | -0.125 [-0.393, +0.134] — inconclusive (CI includes 0) | +0.82 [-0.42, +2.19] — inconclusive (CI includes 0) | -1.426 [-3.453, +0.435] — inconclusive (CI includes 0) |
| lookahead_carat | +10.8 [+1.0, +21.5] — worse (CI excludes 0) | +0.225 [+0.058, +0.425] — better (CI excludes 0) | -1.47 [-2.71, -0.45] — better (CI excludes 0) | +0.797 [+0.043, +1.747] — better (CI excludes 0) |
| ppo_daily | -2.8 [-9.2, +4.0] — inconclusive (CI includes 0) | -0.080 [-0.200, +0.025] — inconclusive (CI includes 0) | +0.44 [-0.21, +1.26] — inconclusive (CI includes 0) | -14.300 [-15.176, -13.556] — worse (CI excludes 0) |

What the data showed (generated):

- 11 methods were run on 20 matched cell(s) each (split: test; seeds: 5). All outcomes are simulated; yields are FAO-33 proxies unless an AquaCrop column is shown. Differences are method − reference.
- Fixed schedule (10 mm / 3 days) vs carat_full: irrigation +173.2 mm (worse (CI excludes 0)); yield proxy +0.013 t/ha (inconclusive (CI includes 0)); cumulative stress -0.51 (inconclusive (CI includes 0)); objective -13.221 (worse (CI excludes 0)); n = 20 pairs.
- Soil-moisture threshold (MAD rule) vs carat_full: irrigation +13.8 mm (worse (CI excludes 0)); yield proxy +0.138 t/ha (inconclusive (CI includes 0)); cumulative stress -1.34 (better (CI excludes 0)); objective -1.678 (worse (CI excludes 0)); n = 20 pairs.
- Standard PPO (no observations) vs carat_full: irrigation -7.5 mm (inconclusive (CI includes 0)); yield proxy -0.291 t/ha (worse (CI excludes 0)); cumulative stress +1.60 (worse (CI excludes 0)); objective -1.893 (inconclusive (CI includes 0)); n = 20 pairs.
- PPO + fixed-interval readings vs carat_full: irrigation +4.0 mm (inconclusive (CI includes 0)); yield proxy -0.112 t/ha (inconclusive (CI includes 0)); cumulative stress +0.30 (inconclusive (CI includes 0)); objective -1.640 (worse (CI excludes 0)); n = 20 pairs.
- PPO + random readings (matched budget) vs carat_full: irrigation -0.5 mm (inconclusive (CI includes 0)); yield proxy -0.086 t/ha (inconclusive (CI includes 0)); cumulative stress +0.25 (inconclusive (CI includes 0)); objective -1.237 (worse (CI excludes 0)); n = 20 pairs.
- PPO + uncertainty-threshold readings vs carat_full: irrigation +10.8 mm (inconclusive (CI includes 0)); yield proxy -0.093 t/ha (inconclusive (CI includes 0)); cumulative stress +0.33 (inconclusive (CI includes 0)); objective -1.590 (inconclusive (CI includes 0)); n = 20 pairs.
- PPO + CARAT readings, no soft risk layer vs carat_full: irrigation -6.0 mm (better (CI excludes 0)); yield proxy -0.123 t/ha (worse (CI excludes 0)); cumulative stress +0.57 (worse (CI excludes 0)); objective -0.969 (worse (CI excludes 0)); n = 20 pairs.
- PPO + CARAT readings, no twin correction vs carat_full: irrigation +5.0 mm (inconclusive (CI includes 0)); yield proxy -0.125 t/ha (inconclusive (CI includes 0)); cumulative stress +0.82 (inconclusive (CI includes 0)); objective -1.426 (inconclusive (CI includes 0)); n = 20 pairs.
- CARAT planner (lookahead action + VOI readings + risk) vs carat_full: irrigation +10.8 mm (worse (CI excludes 0)); yield proxy +0.225 t/ha (better (CI excludes 0)); cumulative stress -1.47 (better (CI excludes 0)); objective +0.797 (better (CI excludes 0)); n = 20 pairs.
- Negative result for the proposed method: lookahead_carat beat carat_full on yield proxy with the CI excluding zero.
- Negative result for the proposed method: lookahead_carat beat carat_full on objective with the CI excluding zero.
- PPO + daily readings (upper-information reference) vs carat_full: irrigation -2.8 mm (inconclusive (CI includes 0)); yield proxy -0.080 t/ha (inconclusive (CI includes 0)); cumulative stress +0.44 (inconclusive (CI includes 0)); objective -14.300 (worse (CI excludes 0)); n = 20 pairs.
- These results come from a simulated reference farm and do not demonstrate field performance.

