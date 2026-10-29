"""Decomposed, normalised reward shared by the RL environment and the evaluator.

    r_t = −λ_w · I_t / 20 mm  −  λ_s · (Ky_t / mean Ky) · (1 − Ks_t)  −  λ_v · max(0, proposed − applied) / 20 mm
    r_T += λ_y · Ya/Ym   (FAO-33 yield-ratio PROXY at season end)

Ks_t is the water-stress coefficient of the simulated farm on day t (the
environment's consequence of the action, delivered as a scalar reward; the
policy never observes the hidden state itself). Observation cost (λ_o per
reading) is NOT charged to PPO because PPO does not control observations in
this design; it is charged in the experiment-level objective instead.
"""
from __future__ import annotations

import numpy as np

from ..config.schemas import ScenarioConfig
from ..carat.lookahead import IRRIGATION_REFERENCE_MM, stress_weight


def daily_reward(scenario: ScenarioConfig, day: int, proposed_mm: float, applied_mm: float, ks: float) -> dict:
    w = scenario.reward
    water = -w.water * applied_mm / IRRIGATION_REFERENCE_MM
    stress = -w.stress * stress_weight(scenario, day) * (1.0 - ks)
    violation = -w.violation * max(0.0, proposed_mm - applied_mm) / IRRIGATION_REFERENCE_MM
    total = water + stress + violation
    if not np.isfinite(total):
        raise FloatingPointError("Non-finite reward")
    return {"reward_water": water, "reward_stress": stress, "reward_violation": violation, "reward": total}


def terminal_reward(scenario: ScenarioConfig, yield_ratio: float) -> float:
    return scenario.reward.terminal_yield * float(yield_ratio)
