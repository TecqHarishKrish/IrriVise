"""End-to-end episode invariants: budgets, determinism, hidden-state isolation, forecast chronology."""
import numpy as np
import pytest

from irrivise_core.data.weather import Season
from irrivise_core.evaluation.runner import run_episode
from irrivise_core.simulation import reference_farm
from irrivise_core.simulation.forecast import ClimatologyForecaster

NON_PPO = ["fixed_schedule", "soil_threshold", "lookahead_carat"]


@pytest.mark.parametrize("method", NON_PPO)
def test_budgets_and_constraints_hold(scenario, seasons, forecaster, method):
    sc = scenario.model_copy(update={"seasonal_budget_mm": 120.0, "observation_budget": 4, "daily_max_mm": 15.0})
    r = run_episode(sc, seasons[-1], forecaster, 3, method)
    s = r.summary
    assert s["seasonal_irrigation_mm"] <= 120 + 1e-9 and s["observation_count"] <= 4
    assert s["max_daily_violations"] == 0 and s["season_budget_violations"] == 0
    assert all(d["applied_mm"] <= 15 for d in r.daily)
    assert s["max_abs_mass_balance_residual_mm"] < 1e-6
    assert len(r.daily) == sc.crop.season_length == len(r.truth)
    assert sum(d["applied_mm"] for d in r.daily) == pytest.approx(s["seasonal_irrigation_mm"])


def test_zero_water_and_zero_observation_budget(scenario, seasons, forecaster):
    sc = scenario.model_copy(update={"seasonal_budget_mm": 0.0, "observation_budget": 0})
    r = run_episode(sc, seasons[0], forecaster, 1, "lookahead_carat")
    assert r.summary["seasonal_irrigation_mm"] == 0 and r.summary["observation_count"] == 0
    assert all(not d["observation_attempted"] for d in r.daily)


def test_deterministic_given_seed(scenario, seasons, forecaster):
    a = run_episode(scenario, seasons[2], forecaster, 7, "lookahead_carat")
    b = run_episode(scenario, seasons[2], forecaster, 7, "lookahead_carat")
    assert a.daily == b.daily and a.truth == b.truth
    c = run_episode(scenario, seasons[2], forecaster, 8, "lookahead_carat")
    assert a.hidden_parameters != c.hidden_parameters


def test_operational_trace_contains_no_hidden_state(scenario, seasons, forecaster):
    r = run_episode(scenario, seasons[0], forecaster, 1, "lookahead_carat")
    keys = set(r.daily[0]) | set(r.decisions[0])
    assert not any(k.startswith("true_") or "reference" in k for k in keys)


def test_decisions_do_not_depend_on_hidden_truth_without_readings(scenario, seasons, forecaster, monkeypatch):
    """Change only the hidden farm's parameters: with no readings, every decision must be identical."""
    sc = scenario.model_copy(update={"observation_budget": 0})
    base = run_episode(sc, seasons[1], forecaster, 5, "lookahead_carat")
    original = reference_farm.draw_soil_parameters

    def wetter(scn, rng, size=None):
        params = original(scn, rng, size)
        if size is None:  # the hidden farm draws with size=None; the twin draws an ensemble
            params["theta_fc"] = params["theta_fc"] * 1.2
            params["init_frac"] = np.array([1.0])
        return params

    # The farm resolves the function from its module; the twin holds its own import, so only the truth changes.
    monkeypatch.setattr(reference_farm, "draw_soil_parameters", wetter)
    changed = run_episode(sc, seasons[1], forecaster, 5, "lookahead_carat")
    assert changed.hidden_parameters != base.hidden_parameters
    assert [d["applied_mm"] for d in changed.daily] == [d["applied_mm"] for d in base.daily]
    assert [d["belief_mean_mm"] for d in changed.daily] == [d["belief_mean_mm"] for d in base.daily]
    assert [t["true_storage_mm"] for t in changed.truth] != [t["true_storage_mm"] for t in base.truth]


def test_future_weather_does_not_affect_past_decisions(scenario, seasons, forecaster):
    s = seasons[3]
    rain = s.rain_mm.copy()
    rain[80:] = rain[80:] + 30.0
    altered = Season(s.season_id, s.dates, rain, s.eto_mm, s.tmin_c, s.tmax_c)
    a = run_episode(scenario, s, forecaster, 2, "lookahead_carat")
    b = run_episode(scenario, altered, forecaster, 2, "lookahead_carat")
    assert a.daily[:80] == b.daily[:80]
    assert a.daily[80:] != b.daily[80:]


def test_forecaster_refuses_future_or_misaligned_history(train):
    fc = ClimatologyForecaster(train)
    with pytest.raises(ValueError):
        fc.forecast(5, [0.0] * 6, [4.0] * 6, 5)
    f = fc.forecast(0, [], [], 5)
    assert len(f.rain_mm) == 5 and f.confidence == "climatology+persistence"
    low = ClimatologyForecaster(None).forecast(3, [1.0, 0.0, 2.0], [4.0, 5.0, 6.0], 3)
    assert low.confidence == "low" and low.eto_mm[0] == pytest.approx(5.0)


def test_ppo_methods_require_a_model(scenario, seasons, forecaster):
    with pytest.raises(ValueError, match="requires a trained PPO model"):
        run_episode(scenario, seasons[0], forecaster, 1, "carat_full")


def test_daily_reference_is_not_budget_limited(scenario, seasons, forecaster):
    from irrivise_core.baselines.policies import MethodSpec
    spec = MethodSpec("daily_ref", "R", "daily", "threshold", "daily")
    r = run_episode(scenario.model_copy(update={"observation_budget": 3}), seasons[0], forecaster, 1, spec)
    assert r.summary["observation_count"] == scenario.crop.season_length
