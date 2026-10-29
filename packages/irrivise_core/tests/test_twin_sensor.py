"""Twin correction, uncertainty dynamics and the budgeted observation gateway."""
import numpy as np
import pytest

from irrivise_core.config.schemas import SensorConfig
from irrivise_core.simulation.reference_farm import ReferenceFarm
from irrivise_core.simulation.sensor import SensorGateway
from irrivise_core.twin.ensemble import EnsembleTwin


@pytest.fixture(scope="module")
def plain(scenario):
    """Scenario with the original unbiased-sensor update (formula checks below assume it)."""
    return scenario.model_copy(update={"twin_bias": scenario.twin_bias.model_copy(update={"method": "none"})})


def test_kalman_update_matches_formulas(plain):
    twin = EnsembleTwin(plain, np.random.default_rng(1))
    w = twin.weights
    mean = float(np.sum(w * twin.storage_mm))
    p = float(np.sum(w * (twin.storage_mm - mean) ** 2))
    z_theta = (mean + 5) / (twin.root_depth_m * 1000)
    r = (0.02 * twin.root_depth_m * 1000) ** 2
    d = twin.correct(z_theta, 0.02)
    k = p / (p + r)
    assert d["gain"] == pytest.approx(k)
    assert d["posterior_var_mm2"] == pytest.approx((1 - k) * p, rel=1e-6, abs=1e-6) or d["clipped_members"] > 0
    assert d["posterior_mean_mm"] == pytest.approx(mean + k * (z_theta * twin.root_depth_m * 1000 - mean), abs=1e-6)
    assert d["posterior_var_mm2"] < p


def test_degenerate_variance_is_safe(plain):
    twin = EnsembleTwin(plain, np.random.default_rng(2))
    twin.storage_mm[:] = twin.storage_mm.mean()
    before = twin.storage_mm.copy()
    d = twin.correct(float(before[0] / (twin.root_depth_m * 1000)) + 0.05, 0.0)
    assert d["gain"] == 0.0 and np.allclose(twin.storage_mm, before)


def test_uncertainty_grows_without_readings(scenario):
    twin = EnsembleTwin(scenario, np.random.default_rng(3))
    twin.correct(float(np.mean(twin.storage_mm)) / (twin.root_depth_m * 1000), 0.005)
    s0 = twin.summary().std_storage_mm
    for _ in range(20):
        twin.predict(0.0, 0.0, 5.0)
    assert twin.summary().std_storage_mm > s0
    assert twin.summary().days_since_observation == 20


def test_outlier_gate_rejects_wild_reading(scenario):
    twin = EnsembleTwin(scenario, np.random.default_rng(4))
    before = twin.storage_mm.copy()
    d = twin.correct(0.79, 0.001, gate_sigma=4.0)
    assert d["applied"] is False and np.allclose(before, twin.storage_mm)


def gateway(scenario, budget, **cfg):
    farm = ReferenceFarm(scenario, np.random.default_rng(0))
    return SensorGateway(farm, SensorConfig(**cfg), budget, np.random.default_rng(1))


def test_budget_charged_exactly_once_per_success(scenario):
    g = gateway(scenario, 3)
    results = [g.measure(d) for d in range(5)]
    assert [r.status for r in results] == ["ok", "ok", "ok", "budget_exhausted", "budget_exhausted"]
    assert g.used == 3 and g.remaining == 0 and len(g.events) == 5


def test_missing_readings_not_charged_unless_configured(scenario):
    g = gateway(scenario, 50, mode="missing", missing_probability=1.0)
    assert all(g.measure(d).status == "missing" for d in range(5)) and g.used == 0
    g2 = gateway(scenario, 2, mode="missing", missing_probability=1.0, charge_failed_attempts=True)
    g2.measure(0), g2.measure(1)
    assert g2.used == 2 and g2.measure(2).status == "budget_exhausted"


def test_zero_budget_never_reads(scenario):
    g = gateway(scenario, 0)
    assert not g.is_available(0) and g.measure(0).status == "budget_exhausted" and g.used == 0


def test_stuck_bias_and_delay_modes(scenario):
    stuck = gateway(scenario, 10, mode="stuck", stuck_after_day=0, noise_std_m3m3=0.01)
    a, b = stuck.measure(0), stuck.measure(1)
    assert a.theta_m3m3 == b.theta_m3m3 and "stuck_sensor_simulated" in a.flags
    biased = gateway(scenario, 10, mode="biased", bias_m3m3=0.05, noise_std_m3m3=0.0)
    nominal = gateway(scenario, 10, noise_std_m3m3=0.0)
    assert biased.measure(0).theta_m3m3 == pytest.approx(nominal.measure(0).theta_m3m3 + 0.05)
    delayed = gateway(scenario, 10, mode="delayed", delay_days=2)
    m = delayed.measure(5)
    assert m.state_day == 3 and "stale" in m.flags
