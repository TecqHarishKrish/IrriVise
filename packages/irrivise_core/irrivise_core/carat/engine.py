"""CARAT — Counterfactual Action-Regret and Adaptive Twin Correction.

A PROPOSED research method (not an established algorithm). For one decision
day, given only the twin's ensemble belief and a legitimate forecast:

1. Q̂(s_k, a) for every plausible state k and feasible action a (lookahead.py).
2. Belief action      a_b  = argmax_a Σ_k w_k Q̂(s_k, a)
   State-informed     a*_k = argmax_a Q̂(s_k, a)
   Estimated regret   R_before = Σ_k w_k [Q̂(s_k, a*_k) − Q̂(s_k, a_b)]  (≥ 0)
   This is an ESTIMATE under the twin's model, not the oracle regret that
   hidden-state knowledge would give.
3. Preposterior value of information: draw M seeded hypothetical readings
   z ~ p(z | belief) (pick member k by weight, add sensor noise); for each z,
   update a COPY of the belief, recompute the preferred action, and compute
   the remaining expected regret under that conditional belief:
       R_after(z) = Σ_k w_k(z) [Q̂(s_k, a*_k) − Q̂(s_k, a_z)]
   GrossVOI = R_before − mean_z R_after(z)
   NetVOI   = GrossVOI − observation_cost − budget_shadow_price_t
4. Observe iff NetVOI > threshold, a reading remains in the budget and the
   gateway is available. High uncertainty alone does not trigger a reading:
   if all plausible states prefer the same action, R_before ≈ 0 ⇒ VOI ≈ 0.

``voi_update='reweight'`` updates the copy by Bayesian likelihood
re-weighting of members (fast, Q̂ reused). ``'kalman'`` applies the same
Kalman ensemble shift as the real correction and recomputes Q̂ (slower).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config.schemas import ScenarioConfig
from ..simulation.forecast import Forecast
from ..twin.ensemble import MemberState
from . import lookahead


@dataclass
class CaratAssessment:
    day: int
    candidate_actions_mm: list[float]
    expected_values: list[float]
    prob_action_best: list[float]
    belief_action_mm: float
    policy_action_mm: float | None
    regret_before: float
    regret_policy_action: float | None
    expected_regret_after: float
    gross_voi: float
    observation_cost: float
    shadow_price: float
    net_voi: float
    observe_recommended: bool
    reason: str
    states_agree: bool
    plausible_states: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def _regret(q: np.ndarray, weights: np.ndarray, action_index: int) -> float:
    return float(np.sum(weights * (q.max(axis=1) - q[:, action_index])))


def _posterior_weights(prior: np.ndarray, storage: np.ndarray, z_mm: float, var_mm2: float) -> np.ndarray:
    var = max(var_mm2, 1e-6)
    log_w = np.log(np.maximum(prior, 1e-300)) - 0.5 * (z_mm - storage) ** 2 / var
    log_w -= log_w.max()
    w = np.exp(log_w)
    return w / w.sum()


class CaratEngine:
    def __init__(self, scenario: ScenarioConfig):
        self.scenario = scenario
        self.config = scenario.carat

    def shadow_price(self, observations_remaining: int, days_remaining: int) -> float:
        """Budget shadow price: base price × scarcity of readings relative to the planned rate.

        scarcity = (budget / season_length) / (remaining / days_remaining). It is
        1 when readings are on plan, > 1 when they are being used up early.
        """
        budget, length = self.scenario.observation_budget, self.scenario.crop.season_length
        if observations_remaining <= 0 or budget <= 0:
            return float("inf")
        planned = budget / length
        current = observations_remaining / max(1, days_remaining)
        return float(self.config.budget_shadow_price * min(10.0, planned / current))

    def assess(self, members: MemberState, forecast: Forecast, day: int, remaining_water_mm: float, observations_remaining: int,
               sensor_available: bool, sensor_std_m3m3: float, rng: np.random.Generator, policy_action_mm: float | None = None,
               compute_voi: bool = True) -> CaratAssessment:
        cfg, scenario = self.config, self.scenario
        actions = lookahead.feasible_actions(scenario.actions_mm, scenario.daily_max_mm, remaining_water_mm)
        q = lookahead.action_values(members, actions, forecast, scenario, day, remaining_water_mm, cfg.horizon_days, cfg.discount,
                                    cfg.terminal_depletion_weight)
        w = members.weights
        expected = (w[:, None] * q).sum(axis=0)
        belief_index = int(np.argmax(expected))
        best = q.argmax(axis=1)
        regret_before = _regret(q, w, belief_index)
        if regret_before < -cfg.regret_tolerance:
            raise ArithmeticError(f"Negative estimated regret {regret_before:.3e}: value model bug")
        regret_before = max(0.0, regret_before)
        prob_best = np.array([float(np.sum(w[best == i])) for i in range(len(actions))])
        policy_regret = None
        if policy_action_mm is not None:
            policy_index = int(np.argmin(np.abs(actions - min(policy_action_mm, actions.max()))))
            policy_regret = max(0.0, _regret(q, w, policy_index))
        states_agree = bool(np.all(best == best[0]))
        days_remaining = scenario.crop.season_length - day
        shadow = self.shadow_price(observations_remaining, days_remaining)
        z_scale = members.root_depth_m * 1000
        sensor_var_mm2 = (sensor_std_m3m3 * z_scale) ** 2
        diagnostics: dict = {"horizon_days": cfg.horizon_days, "ensemble_size": len(w), "voi_update": cfg.voi_update,
                             "forecast_source": forecast.source}
        expected_after = regret_before
        if compute_voi and regret_before > cfg.regret_tolerance:
            draws = []
            members_index = rng.choice(len(w), size=cfg.hypothetical_samples, p=w)
            noise = rng.normal(0.0, np.sqrt(max(sensor_var_mm2, 0.0)), cfg.hypothetical_samples)
            for k, eps in zip(members_index, noise):
                z_mm = float(members.storage_mm[k] + eps)
                if cfg.voi_update == "reweight":
                    post = _posterior_weights(w, members.storage_mm, z_mm, sensor_var_mm2)
                    index = int(np.argmax((post[:, None] * q).sum(axis=0)))
                    draws.append(_regret(q, post, index))
                else:
                    shifted = lookahead.shifted_members(members, z_mm, sensor_var_mm2)
                    q_post = lookahead.action_values(shifted, actions, forecast, scenario, day, remaining_water_mm, cfg.horizon_days,
                                                     cfg.discount, cfg.terminal_depletion_weight)
                    index = int(np.argmax((w[:, None] * q_post).sum(axis=0)))
                    draws.append(_regret(q_post, w, index))
            expected_after = float(np.mean(draws))
            diagnostics["hypothetical_regret_after"] = [round(x, 6) for x in draws]
        elif not compute_voi:
            diagnostics["voi_skipped"] = "VOI not computed for this observation policy"
        else:
            diagnostics["voi_shortcut"] = "regret below tolerance: no reading can change the decision"
        gross = regret_before - expected_after
        if gross < -1e-9:
            diagnostics["negative_gross_voi_sampling_noise"] = gross
        net = gross - cfg.observation_cost - (shadow if np.isfinite(shadow) else 0.0)
        if observations_remaining <= 0:
            observe, reason = False, "observation budget exhausted"
        elif not sensor_available:
            observe, reason = False, "sensor gateway unavailable"
        elif not compute_voi:
            observe, reason = False, "VOI not evaluated"
        elif states_agree and regret_before <= cfg.regret_tolerance:
            observe, reason = False, "all plausible states prefer the same action; estimated regret ≈ 0"
        elif net > cfg.observe_threshold:
            observe, reason = True, f"net VOI {net:.4f} > threshold {cfg.observe_threshold:.4f}"
        else:
            observe, reason = False, f"net VOI {net:.4f} ≤ threshold {cfg.observe_threshold:.4f} (cost {cfg.observation_cost:.3f} + shadow {shadow:.3f})"
        theta = members.storage_mm / z_scale
        order = np.argsort(members.storage_mm)
        plausible = [{"member": int(i), "storage_mm": round(float(members.storage_mm[i]), 3), "theta_m3m3": round(float(theta[i]), 4),
                      "weight": round(float(w[i]), 5), "best_action_mm": float(actions[best[i]]),
                      "q_values": [round(float(x), 5) for x in q[i]]} for i in order]
        return CaratAssessment(
            day=day, candidate_actions_mm=[float(a) for a in actions], expected_values=[round(float(x), 6) for x in expected],
            prob_action_best=[round(float(x), 5) for x in prob_best], belief_action_mm=float(actions[belief_index]),
            policy_action_mm=policy_action_mm, regret_before=regret_before, regret_policy_action=policy_regret,
            expected_regret_after=expected_after, gross_voi=gross, observation_cost=cfg.observation_cost,
            shadow_price=shadow if np.isfinite(shadow) else None, net_voi=net, observe_recommended=observe, reason=reason,
            states_agree=states_agree, plausible_states=plausible, diagnostics=diagnostics)
