"""Sensor-bias handling in the twin: augmented offset state and innovation monitor."""
import numpy as np
import pytest

from irrivise_core.simulation.world import FieldWorld
from irrivise_core.twin.ensemble import EnsembleTwin


def with_bias(scenario, **cfg):
    return scenario.model_copy(update={"twin_bias": scenario.twin_bias.model_copy(update=cfg)})


def test_soil_ensemble_identical_in_every_mode(scenario):
    twins = [EnsembleTwin(with_bias(scenario, method=m), np.random.default_rng(7)) for m in ("none", "innovation_monitor", "augmented")]
    for t in twins[1:]:
        assert np.array_equal(t.storage_mm, twins[0].storage_mm)
    aug = twins[2]
    assert aug.bias_m3m3.mean() == pytest.approx(0.0, abs=1e-12)
    assert aug.bias_m3m3.std() == pytest.approx(scenario.twin_bias.prior_std_m3m3, rel=1e-9)


def test_zero_offset_prior_reduces_to_original_update(scenario):
    a = EnsembleTwin(with_bias(scenario, method="none"), np.random.default_rng(1))
    b = EnsembleTwin(with_bias(scenario, method="augmented", prior_std_m3m3=0.0, drift_std_m3m3=0.0), np.random.default_rng(1))
    z = float(a.storage_mm.mean() + 6) / (a.root_depth_m * 1000)
    da, db = a.correct(z, 0.02), b.correct(z, 0.02)
    assert db["gain"] == pytest.approx(da["gain"], rel=1e-12)
    assert np.allclose(a.storage_mm, b.storage_mm, atol=1e-9)


def test_joint_update_matches_square_root_filter(scenario):
    twin = EnsembleTwin(with_bias(scenario, method="augmented", prior_std_m3m3=0.02), np.random.default_rng(3))
    zs = twin.root_depth_m * 1000
    x = np.vstack([twin.storage_mm, twin.bias_m3m3])
    w = twin.weights
    xm = x @ w
    y = x[0] + x[1] * zs
    h = np.array([1.0, zs])
    cov = ((x - xm[:, None]) * w) @ (x - xm[:, None]).T
    r = (0.02 * zs) ** 2
    s_yy = h @ cov @ h + r
    k = cov @ h / s_yy
    z = float(y @ w + 4.0)
    d = twin.correct(z / zs, 0.02)
    assert d["clipped_members"] == 0
    assert d["gain"] == pytest.approx(k[0], rel=1e-9)
    post = np.vstack([twin.storage_mm, twin.bias_m3m3])
    pm = post @ w
    assert pm == pytest.approx(xm + k * (z - y @ w), rel=1e-9, abs=1e-12)
    post_cov = ((post - pm[:, None]) * w) @ (post - pm[:, None]).T
    expected = (np.eye(2) - np.outer(k, h)) @ cov
    assert post_cov == pytest.approx(expected, rel=1e-6, abs=1e-12)
    assert d["posterior_bias_m3m3"] > 0  # part of a positive innovation is attributed to the sensor


def test_offset_spread_follows_random_walk(scenario):
    cfg = with_bias(scenario, method="augmented", prior_std_m3m3=0.01, drift_std_m3m3=0.003)
    twin = EnsembleTwin(cfg, np.random.default_rng(5))
    var0 = twin.bias_m3m3.var()
    for _ in range(10):
        twin.predict(0.0, 0.0, 5.0)
    assert twin.bias_m3m3.var() == pytest.approx(var0 + 10 * 0.003 ** 2, rel=1e-9)
    assert twin.bias_m3m3.mean() == pytest.approx(0.0, abs=1e-12)  # drift widens, never shifts, the offset belief


def test_effective_sensor_std(scenario):
    none = EnsembleTwin(with_bias(scenario, method="none"), np.random.default_rng(1))
    aug = EnsembleTwin(with_bias(scenario, method="augmented", prior_std_m3m3=0.015), np.random.default_rng(1))
    assert none.effective_sensor_std(0.02) == 0.02
    assert aug.effective_sensor_std(0.02) == pytest.approx(np.hypot(0.02, 0.015))


def test_monitor_flags_and_downweights_persistent_one_sided_readings(scenario):
    twin = EnsembleTwin(with_bias(scenario, method="innovation_monitor", monitor_k=0.5, monitor_h=3.0), np.random.default_rng(2))
    flags = []
    for _ in range(8):
        zs = twin.root_depth_m * 1000
        mean, p = twin.storage_mm.mean(), twin.storage_mm.var()
        z = (mean + 2.0 * np.sqrt(p + (0.02 * zs) ** 2)) / zs  # +2σ every time: persistent, never an outlier
        d = twin.correct(z, 0.02, gate_sigma=4.0)
        flags.append((d["bias_suspected"], d.get("downweighted", False)))
        for _ in range(3):
            twin.predict(0.0, 0.0, 4.0)
    assert not flags[0][0] and any(f[0] for f in flags)
    first = next(i for i, f in enumerate(flags) if f[0])
    assert all(f[1] for f in flags[first + 1:])
    assert twin.bias_state()["bias_suspected"]


def _mean_twin_error(scenario, seasons, forecaster, method):
    errors = []
    for season in seasons:
        for seed in (1, 2):
            world = FieldWorld(with_bias(scenario, method=method), season, forecaster, seed)
            est, true = [], []
            while not world.done:
                if world.day % 7 == 3:
                    world.observe()
                farm = world.apply(5.0 if world.day % 3 == 0 else 0.0)
                est.append(world.twin.summary().mean_storage_mm)
                true.append(farm.storage_mm)
            errors.append(np.mean(np.array(est) - np.array(true)))
    return float(np.mean(errors))


def test_augmented_twin_resists_wet_biased_sensor(scenario, seasons, forecaster, split):
    biased = scenario.model_copy(update={"observation_budget": 30,
                                         "sensor": scenario.sensor.model_copy(update={"mode": "biased", "bias_m3m3": 0.03})})
    val = [s for s in seasons if s.season_id in split.validation][:2]
    plain = _mean_twin_error(biased, val, forecaster, "none")
    aug = _mean_twin_error(biased, val, forecaster, "augmented")
    assert plain > 4.0            # unbiased update is dragged wet by the sensor
    assert aug < 0.4 * plain      # the offset state absorbs most of it


def test_augmented_twin_unchanged_without_a_fault(scenario, seasons, forecaster, split):
    nominal = scenario.model_copy(update={"observation_budget": 30})
    val = [s for s in seasons if s.season_id in split.validation][:2]
    plain = _mean_twin_error(nominal, val, forecaster, "none")
    aug = _mean_twin_error(nominal, val, forecaster, "augmented")
    assert abs(aug - plain) < 2.0


def test_forecast_step_decouples_offset_from_storage(scenario):
    twin = EnsembleTwin(with_bias(scenario, method="augmented"), np.random.default_rng(9))
    zs = twin.root_depth_m * 1000
    twin.correct(float(twin.storage_mm.mean() + 10) / zs, 0.02)
    w = twin.weights
    cov = lambda a, b: float(np.sum(w * (a - np.sum(w * a)) * (b - np.sum(w * b))))  # noqa: E731
    assert cov(twin.storage_mm, twin.bias_m3m3) < 0  # the update correlates them
    var_b = cov(twin.bias_m3m3, twin.bias_m3m3)
    twin.predict(0.0, 0.0, 5.0)
    assert cov(twin.storage_mm, twin.bias_m3m3) == pytest.approx(0.0, abs=1e-12)
    drift = scenario.twin_bias.drift_std_m3m3
    assert cov(twin.bias_m3m3, twin.bias_m3m3) == pytest.approx(var_b + drift ** 2, rel=1e-9)


def test_storage_gain_never_negative_over_a_season(scenario, seasons, forecaster, split):
    """Regression: a stale storage–offset anti-correlation used to flip the gain sign mid-season."""
    world = FieldWorld(with_bias(scenario.model_copy(update={"observation_budget": 40}), method="augmented"),
                       [s for s in seasons if s.season_id in split.validation][0], forecaster, 1)
    gains = []
    while not world.done:
        if world.day % 4 == 1:
            _, d = world.observe()
            if d and d["applied"]:
                gains.append(d["gain"])
        world.apply(5.0 if world.day % 3 == 0 else 0.0)
    assert len(gains) > 20 and min(gains) > 0
