"""Same-horizon, same-objective action-value model used by CARAT and the risk manager.

Q̂(s_k, a) = Σ_{h=0}^{H-1} γ^h r_h  −  γ^H · w_T · max(0, Dr_H − RAW_H) / TAW_H

* Day h = 0 applies candidate irrigation ``a``; days h ≥ 1 follow a documented
  rollout policy ("refill when depletion exceeds RAW", rounded up to the
  action grid, within the remaining seasonal budget and daily cap).
* Weather on every lead day is the FORECAST (never realized weather).
* r_h uses the same reward weights as the RL environment:
      r_h = −λ_w · I_h / I_ref − λ_s · (Ky_h / mean Ky) · (1 − Ks_h)
* All members and actions are evaluated with identical horizon, forecast and
  objective, so Q̂ values are comparable across actions.

The terminal depletion term is a crude bootstrap so a short horizon does not
ignore end-of-horizon dryness. It is an approximation, not the PPO critic.
"""
from __future__ import annotations

import numpy as np

from ..config.schemas import ScenarioConfig
from ..simulation import water_balance as wb
from ..simulation.forecast import Forecast
from ..twin.ensemble import MemberState

IRRIGATION_REFERENCE_MM = 20.0


def feasible_actions(actions_mm: tuple[float, ...], daily_max_mm: float, remaining_mm: float) -> np.ndarray:
    """Discrete action grid projected onto the hard limits (deduplicated, ascending)."""
    cap = max(0.0, min(daily_max_mm, remaining_mm))
    return np.unique(np.minimum(np.asarray(actions_mm, dtype=float), cap))


def stress_weight(scenario: ScenarioConfig, day: int) -> float:
    ky = scenario.crop.ky_stage
    calendar = wb.CropCalendar(scenario.crop)
    return float(calendar.ky(min(day, calendar.length - 1)) / max(1e-9, np.mean(ky)))


def action_values(members: MemberState, actions: np.ndarray, forecast: Forecast, scenario: ScenarioConfig, day: int,
                  remaining_mm: float, horizon: int, discount: float, terminal_weight: float) -> np.ndarray:
    """Return Q̂ with shape (K members, A actions)."""
    calendar = wb.CropCalendar(scenario.crop)
    rw = scenario.reward
    k, a = len(members.storage_mm), len(actions)
    col = lambda x: np.asarray(x, dtype=float)[:, None]  # noqa: E731
    wp, fc, sat, tau, cn, em, sub = (col(x) for x in (members.theta_wp, members.theta_fc, members.theta_sat, members.tau,
                                                       members.cn, members.et_mult, members.subsoil_frac))
    storage = np.repeat(col(members.storage_mm), a, axis=1)
    budget = np.full((k, a), float(remaining_mm))
    grid = np.asarray(scenario.actions_mm, dtype=float)
    p = scenario.crop.depletion_p
    zr = members.root_depth_m
    q = np.zeros((k, a))
    horizon = int(min(horizon, len(forecast.rain_mm)))
    for h in range(horizon):
        d = day + h
        if d >= calendar.length:
            break
        if h == 0:
            irrigation = np.broadcast_to(actions[None, :], (k, a)).astype(float)
        else:
            z = zr * 1000
            depletion = np.maximum(0.0, fc * z - storage)
            raw = p * (fc - wp) * z
            need = np.where(depletion > raw, depletion, 0.0)
            # round the refill up to the action grid, then respect hard limits
            index = np.minimum(np.searchsorted(grid, need, side="left"), len(grid) - 1)
            irrigation = np.where(need > 0, grid[index], 0.0)
            irrigation = np.minimum(irrigation, np.minimum(scenario.daily_max_mm, np.maximum(0.0, budget)))
        zr_next = calendar.root_depth(d + 1)
        flux = wb.step(storage, wp, fc, sat, tau, cn, zr, zr_next, float(forecast.rain_mm[h]), irrigation,
                       float(forecast.eto_mm[h]), calendar.kc(d), p, sub, et_multiplier=em, check=False)
        reward = -rw.water * irrigation / IRRIGATION_REFERENCE_MM - rw.stress * stress_weight(scenario, d) * (1.0 - flux.ks)
        q += discount ** h * reward
        storage = flux.storage_mm
        budget = budget - irrigation
        zr = zr_next
    z = zr * 1000
    taw = (fc - wp) * z
    excess = np.maximum(0.0, np.maximum(0.0, fc * z - storage) - p * taw) / taw
    q -= discount ** horizon * terminal_weight * excess
    if not np.all(np.isfinite(q)):
        raise FloatingPointError("Non-finite action values in CARAT lookahead")
    return q


def shifted_members(members: MemberState, measurement_mm: float, sensor_var_mm2: float) -> MemberState:
    """Kalman ensemble shift used for hypothetical (VOI) and real corrections alike."""
    w = members.weights
    mean = float(np.sum(w * members.storage_mm))
    var = float(np.sum(w * (members.storage_mm - mean) ** 2))
    var = 0.0 if var < 1e-12 else var
    gain = var / (var + sensor_var_mm2) if var + sensor_var_mm2 > 0 else 0.0
    new = mean + gain * (measurement_mm - mean) + np.sqrt(max(0.0, 1 - gain)) * (members.storage_mm - mean)
    z = members.root_depth_m * 1000
    new = np.clip(new, members.theta_wp * z, members.theta_sat * z)
    return MemberState(new, members.theta_wp, members.theta_fc, members.theta_sat, members.tau, members.cn, members.et_mult,
                       members.subsoil_frac, members.weights, members.root_depth_m, members.day)
