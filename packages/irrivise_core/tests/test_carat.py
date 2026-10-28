"""CARAT regret / VOI behaviour on deterministic toy beliefs, and the risk manager."""
import numpy as np
import pytest

from irrivise_core.carat.engine import CaratEngine
from irrivise_core.carat.lookahead import action_values, feasible_actions
from irrivise_core.carat.risk import RiskManager, hard_project
from irrivise_core.simulation.forecast import Forecast
from irrivise_core.twin.ensemble import MemberState


def members_at(scenario, theta_values, day=50):
    from irrivise_core.simulation.water_balance import CropCalendar

    zr = CropCalendar(scenario.crop).root_depth(day)
    z = zr * 1000
    fc = scenario.soil.theta_fc
    k = len(theta_values)
    return MemberState(np.array(theta_values) * z, np.full(k, scenario.soil.theta_wp), np.full(k, fc), np.full(k, scenario.soil.theta_sat),
                       np.full(k, scenario.soil.drainage_tau), np.full(k, scenario.soil.curve_number), np.ones(k), np.full(k, 0.7), np.full(k, 1 / k), zr, day)


DRY = Forecast(np.zeros(5), np.full(5, 6.0), np.zeros(5), "test", "test")


def test_identical_states_give_zero_regret_and_skip(scenario):
    engine = CaratEngine(scenario)
    members = members_at(scenario, [0.2] * 20)
    a = engine.assess(members, DRY, 50, 300, 10, True, 0.02, np.random.default_rng(0))
    assert a.states_agree and a.regret_before == pytest.approx(0, abs=1e-12)
    assert a.observe_recommended is False and "same action" in a.reason


def test_disagreeing_states_have_positive_regret_and_voi(scenario):
    engine = CaratEngine(scenario.model_copy(update={"carat": scenario.carat.model_copy(update={"observation_cost": 0.0, "budget_shadow_price": 0.0})}))
    thetas = list(np.linspace(scenario.soil.theta_wp + 0.005, scenario.soil.theta_fc + 0.02, 20))
    members = members_at(scenario, thetas)
    a = engine.assess(members, DRY, 50, 300, 10, True, 0.005, np.random.default_rng(0))
    assert not a.states_agree and a.regret_before > 0
    assert a.expected_regret_after < a.regret_before and a.gross_voi > 0
    assert a.observe_recommended
    q = action_values(members, feasible_actions(scenario.actions_mm, 20, 300), DRY, scenario, 50, 300, 5, 0.97, 0.5)
    assert q.shape == (20, 5) and np.all(np.isfinite(q))


def test_costs_and_budget_block_observation(scenario):
    thetas = list(np.linspace(scenario.soil.theta_wp + 0.005, scenario.soil.theta_fc + 0.02, 20))
    members = members_at(scenario, thetas)
    expensive = CaratEngine(scenario.model_copy(update={"carat": scenario.carat.model_copy(update={"observation_cost": 100.0})}))
    assert not expensive.assess(members, DRY, 50, 300, 10, True, 0.005, np.random.default_rng(0)).observe_recommended
    a = CaratEngine(scenario).assess(members, DRY, 50, 300, 0, True, 0.005, np.random.default_rng(0))
    assert not a.observe_recommended and a.reason == "observation budget exhausted"


def test_shadow_price_rises_when_readings_are_spent_early(scenario):
    engine = CaratEngine(scenario)
    on_plan = engine.shadow_price(observations_remaining=5, days_remaining=70)
    early = engine.shadow_price(observations_remaining=1, days_remaining=120)
    assert early > on_plan > 0 and engine.shadow_price(0, 10) == float("inf")


def test_voi_kalman_mode_runs(scenario):
    engine = CaratEngine(scenario.model_copy(update={"carat": scenario.carat.model_copy(update={"voi_update": "kalman", "hypothetical_samples": 4})}))
    thetas = list(np.linspace(scenario.soil.theta_wp + 0.01, scenario.soil.theta_fc, 20))
    a = engine.assess(members_at(scenario, thetas, 60), DRY, 60, 300, 10, True, 0.02, np.random.default_rng(1))
    assert np.isfinite(a.net_voi) and len(a.diagnostics["hypothetical_regret_after"]) == 4


def test_hard_projection():
    assert hard_project(20, 20, 7) == (7, "projected_budget")
    assert hard_project(20, 15, 100) == (15, "projected_daily_cap")
    assert hard_project(10, 20, 0) == (0, "budget_exhausted")
    assert hard_project(-5, 20, 100) == (0, "ok")


def test_soft_risk_raises_dry_sensitive_stage_and_can_be_disabled(scenario):
    day = sum(scenario.crop.stage_lengths_days[:2]) + 5  # mid-season, Ky = 1.5
    members = members_at(scenario, [scenario.soil.theta_wp + 0.01] * 20, day)
    on = RiskManager(scenario).project(0.0, members, DRY, day, 300)
    assert on.applied_mm > 0 and any("soft risk" in r for r in on.reasons)
    off = RiskManager(scenario, soft_enabled=False).project(0.0, members, DRY, day, 300)
    assert off.applied_mm == 0 and "elevated_stress_risk_sensitive_stage" in off.risk_flags
    empty = RiskManager(scenario).project(20.0, members, DRY, day, 0)
    assert empty.applied_mm == 0 and empty.constraint_status == "budget_exhausted"
