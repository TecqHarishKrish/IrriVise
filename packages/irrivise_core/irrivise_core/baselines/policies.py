"""Irrigation policies, observation policies and the experiment method registry.

Every policy receives only an AgentView (and, for CARAT-aware components, a
copy of the twin's ensemble). None can reach the hidden reference farm.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..carat.engine import CaratAssessment
from ..carat.lookahead import feasible_actions
from ..config.schemas import ScenarioConfig
from ..simulation.world import AgentView


class IrrigationPolicy(Protocol):
    name: str

    def propose(self, view: AgentView) -> float: ...


@dataclass
class FixedSchedulePolicy:
    """B0: irrigate ``depth_mm`` every ``interval_days`` days (information-free)."""

    interval_days: int = 3
    depth_mm: float = 10.0
    name: str = "fixed_schedule"

    def propose(self, view: AgentView) -> float:
        return self.depth_mm if view.day % self.interval_days == 0 else 0.0


@dataclass
class SoilThresholdPolicy:
    """B1: FAO-56 management-allowed depletion rule on the twin's ESTIMATE.

    Irrigate when estimated depletion ≥ ``trigger`` × TAW (default = crop p,
    i.e. Dr ≥ RAW), refilling towards field capacity rounded up to the action grid.
    """

    scenario: ScenarioConfig
    trigger: float | None = None
    name: str = "soil_threshold"

    def propose(self, view: AgentView) -> float:
        trigger = self.scenario.crop.depletion_p if self.trigger is None else self.trigger
        if view.belief.depletion_fraction < trigger:
            return 0.0
        grid = np.asarray(self.scenario.actions_mm)
        need = view.belief.depletion_mm
        return float(grid[min(len(grid) - 1, int(np.searchsorted(grid, need)))])


@dataclass
class LookaheadPolicy:
    """Belief-optimal action of the CARAT value model (planner without PPO)."""

    name: str = "lookahead_planner"

    def propose(self, view: AgentView) -> float:  # resolved by the runner, which owns the assessment
        raise RuntimeError("LookaheadPolicy is resolved by the episode runner")


# -- observation policies ---------------------------------------------------------

class ObservationPolicy(Protocol):
    name: str
    needs_voi: bool

    def decide(self, view: AgentView, assessment: CaratAssessment | None, rng: np.random.Generator) -> tuple[bool, str]: ...


@dataclass
class NoObservation:
    name: str = "none"
    needs_voi: bool = False

    def decide(self, view, assessment, rng):
        return False, "no observation policy"


@dataclass
class DailyObservation:
    """Upper-information reference: a reading every day while budget lasts (NOT budget-matched)."""

    name: str = "daily"
    needs_voi: bool = False

    def decide(self, view, assessment, rng):
        return view.remaining_observations > 0, "daily reading (upper-information reference)"


@dataclass
class FixedIntervalObservation:
    """B3: evenly spaced readings that exactly spend the budget over the season."""

    name: str = "fixed_interval"
    needs_voi: bool = False

    def decide(self, view, assessment, rng):
        if view.observation_budget <= 0 or view.remaining_observations <= 0:
            return False, "observation budget exhausted"
        interval = view.season_length / view.observation_budget
        due = int(np.floor(view.day / interval)) >= view.observation_budget - view.remaining_observations
        return bool(due), f"scheduled every {interval:.1f} days"


@dataclass
class RandomObservation:
    """B4: seeded Bernoulli readings at the matched expected rate (budget/season)."""

    name: str = "random"
    needs_voi: bool = False

    def decide(self, view, assessment, rng):
        if view.remaining_observations <= 0:
            return False, "observation budget exhausted"
        rate = view.observation_budget / view.season_length
        draw = float(rng.random())
        return draw < rate, f"random draw {draw:.3f} vs rate {rate:.3f}"


@dataclass
class UncertaintyThresholdObservation:
    """B5: observe when twin std / TAW exceeds a threshold (tuned on validation)."""

    threshold: float = 0.08
    name: str = "uncertainty_threshold"
    needs_voi: bool = False

    def decide(self, view, assessment, rng):
        if view.remaining_observations <= 0:
            return False, "observation budget exhausted"
        ratio = view.belief.std_storage_mm / max(view.belief.taw_mm, 1e-6)
        return ratio > self.threshold, f"std/TAW {ratio:.3f} vs threshold {self.threshold:.3f}"


@dataclass
class CaratObservation:
    """CARAT: observe iff estimated net VOI exceeds the threshold."""

    name: str = "carat_voi"
    needs_voi: bool = True

    def decide(self, view, assessment, rng):
        if assessment is None:
            return False, "no CARAT assessment"
        return assessment.observe_recommended, assessment.reason


# -- method registry -------------------------------------------------------------

@dataclass(frozen=True)
class MethodSpec:
    key: str
    code: str
    label: str
    irrigation: str            # fixed | threshold | ppo | lookahead
    observation: str           # none | fixed_interval | random | uncertainty_threshold | carat | daily
    correction: bool = True
    soft_risk: bool = False
    needs_model: bool = False
    role: str = "baseline"     # baseline | ablation | proposed | reference
    note: str = ""

    def as_dict(self) -> dict:
        return dict(self.__dict__)


METHODS: dict[str, MethodSpec] = {m.key: m for m in (
    MethodSpec("fixed_schedule", "B0", "Fixed schedule (10 mm / 3 days)", "fixed", "none", note="Information-free calendar schedule"),
    MethodSpec("soil_threshold", "B1", "Soil-moisture threshold (MAD rule)", "threshold", "fixed_interval",
               note="FAO-56 RAW trigger on the twin estimate, corrected by evenly spaced readings"),
    MethodSpec("ppo", "B2", "Standard PPO (no observations)", "ppo", "none", needs_model=True),
    MethodSpec("ppo_fixed_interval", "B3", "PPO + fixed-interval readings", "ppo", "fixed_interval", needs_model=True),
    MethodSpec("ppo_random", "B4", "PPO + random readings (matched budget)", "ppo", "random", needs_model=True),
    MethodSpec("ppo_uncertainty", "B5", "PPO + uncertainty-threshold readings", "ppo", "uncertainty_threshold", needs_model=True),
    MethodSpec("ppo_carat_no_risk", "A5", "PPO + CARAT readings, no soft risk layer", "ppo", "carat", needs_model=True, role="ablation",
               note="Hard limits still enforced; only the soft risk layer is removed"),
    MethodSpec("ppo_carat_no_correction", "A6", "PPO + CARAT readings, no twin correction", "ppo", "carat", correction=False,
               soft_risk=True, needs_model=True, role="ablation",
               note="Diagnostic: readings are taken and charged but discarded; isolates the value of correction"),
    MethodSpec("carat_full", "P", "Full CARAT (PPO + VOI readings + correction + risk)", "ppo", "carat", soft_risk=True,
               needs_model=True, role="proposed"),
    MethodSpec("lookahead_carat", "P-noPPO", "CARAT planner (lookahead action + VOI readings + risk)", "lookahead", "carat",
               soft_risk=True, role="reference", note="Uses the CARAT value model as the irrigation policy; available before PPO training"),
    MethodSpec("ppo_daily", "R-daily", "PPO + daily readings (upper-information reference)", "ppo", "daily", needs_model=True,
               role="reference", note="Not budget-matched: uses one reading per day"),
)}


def observation_policy(name: str, uncertainty_threshold: float = 0.08) -> ObservationPolicy:
    return {
        "none": NoObservation(), "daily": DailyObservation(), "fixed_interval": FixedIntervalObservation(),
        "random": RandomObservation(), "uncertainty_threshold": UncertaintyThresholdObservation(uncertainty_threshold),
        "carat": CaratObservation(),
    }[name]


def lookahead_actions(scenario: ScenarioConfig, remaining_mm: float) -> np.ndarray:
    return feasible_actions(scenario.actions_mm, scenario.daily_max_mm, remaining_mm)
