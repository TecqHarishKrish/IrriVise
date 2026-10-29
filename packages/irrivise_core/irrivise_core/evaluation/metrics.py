"""Post-run metrics derived ONLY from saved traces (re-derivable from exports).

Definitions (units in names):
* seasonal_irrigation_mm      Σ applied irrigation
* yield_proxy_t_ha            FAO-33 ratio × crop max_yield_t_ha — a PROXY, not measured / AquaCrop yield
* irrigation_wp_proxy_kg_m3   yield_proxy (kg/ha) / (irrigation mm × 10 m³/ha·mm); null if irrigation = 0
* total_wp_proxy_kg_m3        yield_proxy (kg/ha) / ((irrigation + rain) mm × 10)
* cumulative_stress           Σ_t (1 − Ks_t) of the simulated farm (stress-days equivalent)
* weighted_stress             Σ_t (Ky_t / mean Ky)(1 − Ks_t)
* stress_days                 days with Ks_t < 1
* twin_rmse_mm / _m3m3        RMSE of the end-of-day twin mean vs hidden reference storage
* estimated_regret_mean       mean CARAT estimated regret (model estimate, not oracle regret)
* max_daily_violations / season_budget_violations   must be 0 (hard constraints)
"""
from __future__ import annotations

import numpy as np

from ..config.schemas import ScenarioConfig


def compute_summary(scenario: ScenarioConfig, spec, daily: list[dict], truth: list[dict], evaluation: dict, total_reward: float,
                    terminal_reward: float, runtime_s: float, sensor) -> dict:
    applied = np.array([d["applied_mm"] for d in daily], dtype=float)
    rain = np.array([d["rain_mm"] for d in daily], dtype=float)
    ks = np.array([t["true_ks"] for t in truth], dtype=float)
    ky = np.array([d["ky"] for d in daily], dtype=float)
    est = np.array([t["estimate_end_mm"] for t in truth], dtype=float)
    true = np.array([t["true_storage_mm"] for t in truth], dtype=float)
    end_roots = np.array([t["root_depth_end_m"] for t in truth], dtype=float)
    residual = np.array([t["mass_balance_residual_mm"] for t in truth], dtype=float)
    regrets = [d["est_regret"] for d in daily if d["est_regret"] is not None]
    vois = [d["gross_voi"] for d in daily if d["gross_voi"] is not None]
    net_vois = [d["net_voi"] for d in daily if d["net_voi"] is not None]
    disagree = [abs(d["initial_action_mm"] - d["proposed_mm"]) > 1e-9 for d in daily]
    seasonal = float(applied.sum())
    ratio = float(evaluation["yield_ratio"])
    yield_t = ratio * scenario.crop.max_yield_t_ha
    irrigation_m3_ha = seasonal * 10.0
    total_m3_ha = (seasonal + float(rain.sum())) * 10.0
    daily_violations = int(np.sum(applied > scenario.daily_max_mm + 1e-9) + np.sum(applied < -1e-12))
    season_violation = int(seasonal > scenario.seasonal_budget_mm + 1e-6)
    observation_count = int(sensor.used)
    obs_cost = scenario.reward.observation * observation_count
    theta_err = (est - true) / (end_roots * 1000.0)
    return {
        "method": spec.key, "method_code": spec.code, "method_label": spec.label, "days": len(daily),
        "seasonal_irrigation_mm": round(seasonal, 3), "seasonal_rain_mm": round(float(rain.sum()), 3),
        "irrigation_events": int(np.sum(applied > 0)),
        "yield_ratio_proxy": round(ratio, 5), "yield_proxy_t_ha": round(yield_t, 4),
        "irrigation_wp_proxy_kg_m3": round(yield_t * 1000 / irrigation_m3_ha, 4) if irrigation_m3_ha > 0 else None,
        "total_wp_proxy_kg_m3": round(yield_t * 1000 / total_m3_ha, 4) if total_m3_ha > 0 else None,
        "cumulative_stress": round(float(np.sum(1 - ks)), 4),
        "weighted_stress": round(float(np.sum((ky / max(1e-9, np.mean(scenario.crop.ky_stage))) * (1 - ks))), 4),
        "stress_days": int(np.sum(ks < 1 - 1e-9)),
        "observation_count": observation_count, "observation_attempts": int(sensor.attempts),
        "observations_remaining": int(sensor.remaining),
        "observation_use_rate": round(observation_count / scenario.observation_budget, 4) if scenario.observation_budget > 0 else None,
        "twin_rmse_mm": round(float(np.sqrt(np.mean((est - true) ** 2))), 4),
        "twin_rmse_m3m3": round(float(np.sqrt(np.mean(theta_err ** 2))), 5),
        "twin_bias_mm": round(float(np.mean(est - true)), 4),
        "estimated_regret_mean": round(float(np.mean(regrets)), 6) if regrets else None,
        "estimated_regret_sum": round(float(np.sum(regrets)), 6) if regrets else None,
        "gross_voi_mean": round(float(np.mean(vois)), 6) if vois else None,
        "net_voi_mean": round(float(np.mean(net_vois)), 6) if net_vois else None,
        "decision_disagreement_rate": round(float(np.mean(disagree)), 4) if disagree else None,
        "total_reward": round(total_reward, 5), "terminal_reward": round(terminal_reward, 5),
        "objective_with_observation_cost": round(total_reward - obs_cost, 5),
        "max_daily_violations": daily_violations, "season_budget_violations": season_violation,
        "max_abs_mass_balance_residual_mm": float(np.max(np.abs(residual))) if len(residual) else 0.0,
        "runtime_seconds": round(runtime_s, 4),
        "yield_label": "yield PROXY (FAO-33 stage ratio × max yield); not measured, not AquaCrop",
    }
