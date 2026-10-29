"""Risk manager: hard action constraints + soft, model-based crop-stress risk.

HARD constraints (always enforced, cannot be disabled):
  0 ≤ applied ≤ daily maximum, applied ≤ remaining seasonal water. The
  proposed depth is projected down onto the feasible interval and the delta
  is logged.

SOFT risk layer (configurable; disabled in the "no risk manager" ablation):
  uses the twin's plausible states and the 1-day forecast to estimate, for each
  feasible candidate, P(Ks < 1 tomorrow) and the expected irrigation loss to
  drainage/runoff. These are UNCERTAIN MODEL ESTIMATES, not guarantees.
  * In stress-sensitive stages (Ky ≥ sensitive_ky), if P(stress) of the
    projected action exceeds ``max_stress_probability``, raise to the
    smallest feasible depth that meets it; if none does, apply the largest
    feasible depth and flag ``unmet_stress_risk``.
  * Otherwise, if more than ``max_waste_fraction`` of the irrigation is
    expected to be lost, reduce to the largest smaller depth whose stress
    probability is no worse than the projected action's.
The manager returns a decision; it never touches the reference farm.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config.schemas import ScenarioConfig
from ..simulation import water_balance as wb
from ..simulation.forecast import Forecast
from ..twin.ensemble import MemberState
from .lookahead import feasible_actions


@dataclass
class RiskDecision:
    proposed_mm: float
    hard_projected_mm: float
    applied_mm: float
    constraint_status: str              # ok | projected_daily_cap | projected_budget | budget_exhausted
    reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    stress_probability: dict[str, float] = field(default_factory=dict)
    predicted_stress_quantiles: dict[str, float] = field(default_factory=dict)
    expected_loss_fraction: float | None = None
    soft_layer_enabled: bool = True

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def hard_project(proposed_mm: float, daily_max_mm: float, remaining_mm: float) -> tuple[float, str]:
    if not np.isfinite(proposed_mm):
        raise ValueError("Proposed irrigation must be finite")
    remaining = max(0.0, remaining_mm)
    applied = min(max(0.0, proposed_mm), daily_max_mm, remaining)
    if remaining <= 0 and proposed_mm > 0:
        return 0.0, "budget_exhausted"
    if proposed_mm > daily_max_mm and applied == daily_max_mm:
        return applied, "projected_daily_cap"
    if proposed_mm > remaining and applied == remaining:
        return applied, "projected_budget"
    return applied, "ok"


class RiskManager:
    def __init__(self, scenario: ScenarioConfig, soft_enabled: bool | None = None):
        self.scenario = scenario
        self.config = scenario.risk
        self.soft_enabled = self.config.enabled if soft_enabled is None else soft_enabled
        self.calendar = wb.CropCalendar(scenario.crop)

    def _one_day(self, members: MemberState, actions: np.ndarray, forecast: Forecast, day: int):
        col = lambda x: np.asarray(x, dtype=float)[:, None]  # noqa: E731
        k, a = len(members.storage_mm), len(actions)
        storage = np.repeat(col(members.storage_mm), a, axis=1)
        flux = wb.step(storage, col(members.theta_wp), col(members.theta_fc), col(members.theta_sat), col(members.tau), col(members.cn),
                       members.root_depth_m, self.calendar.root_depth(day + 1), float(forecast.rain_mm[0]),
                       np.broadcast_to(actions[None, :], (k, a)).astype(float), float(forecast.eto_mm[0]),
                       self.calendar.kc(min(day, self.calendar.length - 1)), self.scenario.crop.depletion_p,
                       col(members.subsoil_frac), et_multiplier=col(members.et_mult), check=False)
        # stress probability uses end-of-day depletion relative to RAW (next-day stress state)
        z = self.calendar.root_depth(day + 1) * 1000
        raw = self.scenario.crop.depletion_p * (col(members.theta_fc) - col(members.theta_wp)) * z
        stressed = flux.depletion_mm > raw
        loss = flux.drainage_mm + flux.runoff_mm
        return flux, stressed, loss

    def project(self, proposed_mm: float, members: MemberState, forecast: Forecast, day: int, remaining_mm: float) -> RiskDecision:
        sc = self.scenario
        projected, status = hard_project(proposed_mm, sc.daily_max_mm, remaining_mm)
        decision = RiskDecision(proposed_mm=float(proposed_mm), hard_projected_mm=projected, applied_mm=projected,
                                constraint_status=status, soft_layer_enabled=self.soft_enabled)
        if status != "ok":
            decision.reasons.append(f"hard constraint: {status.replace('_', ' ')} ({proposed_mm:g} → {projected:g} mm)")
        candidates = np.unique(np.append(feasible_actions(sc.actions_mm, sc.daily_max_mm, remaining_mm), projected))
        flux, stressed, loss = self._one_day(members, candidates, forecast, day)
        w = members.weights
        p_stress = (w[:, None] * stressed).sum(axis=0)
        loss_mean = (w[:, None] * loss).sum(axis=0)
        decision.stress_probability = {f"{a:g}": round(float(p), 4) for a, p in zip(candidates, p_stress)}
        idx = int(np.where(candidates == projected)[0][0])
        applied = projected
        sensitive = self.calendar.ky(min(day, self.calendar.length - 1)) >= self.config.sensitive_ky
        if p_stress[idx] > self.config.max_stress_probability:
            decision.risk_flags.append("elevated_stress_risk" + ("_sensitive_stage" if sensitive else ""))
        if self.soft_enabled:
            if sensitive and p_stress[idx] > self.config.max_stress_probability:
                better = [i for i in range(len(candidates)) if candidates[i] > projected and p_stress[i] <= self.config.max_stress_probability]
                if better:
                    applied = float(candidates[better[0]])
                    decision.reasons.append(f"soft risk: raised {projected:g} → {applied:g} mm; estimated P(stress) {p_stress[idx]:.2f} > {self.config.max_stress_probability:.2f} in a stress-sensitive stage")
                else:
                    applied = float(candidates.max())
                    decision.risk_flags.append("unmet_stress_risk")
                    decision.reasons.append(f"soft risk: no feasible depth meets the stress target; applying largest feasible {applied:g} mm")
            elif projected > 0:
                waste = float((loss_mean[idx] - loss_mean[0]) / projected)
                decision.expected_loss_fraction = round(waste, 4)
                if waste > self.config.max_waste_fraction:
                    smaller = [i for i in range(len(candidates)) if candidates[i] < projected and p_stress[i] <= max(p_stress[idx], self.config.max_stress_probability)]
                    if smaller:
                        applied = float(candidates[smaller[-1]])
                        decision.reasons.append(f"soft risk: reduced {projected:g} → {applied:g} mm; {100 * waste:.0f}% of irrigation expected lost to drainage/runoff")
                        decision.risk_flags.append("waste_reduction")
        decision.applied_mm = applied
        j = int(np.where(candidates == applied)[0][0])
        stress = 1.0 - flux.ks[:, j]
        order = np.argsort(stress)
        cdf = np.cumsum(w[order])
        quant = lambda q: float(stress[order][min(len(stress) - 1, np.searchsorted(cdf, q))])  # noqa: E731
        decision.predicted_stress_quantiles = {"p10": round(quant(0.1), 4), "p50": round(quant(0.5), 4), "p90": round(quant(0.9), 4)}
        if remaining_mm - applied <= 0 and sc.seasonal_budget_mm > 0:
            decision.risk_flags.append("water_budget_exhausted")
        return decision
