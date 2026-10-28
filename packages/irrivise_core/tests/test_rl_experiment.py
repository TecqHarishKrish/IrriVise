"""Gymnasium environment, PPO training/checkpoint verification, matched experiments, AquaCrop."""
import json
import shutil

import numpy as np
import pytest
from stable_baselines3.common.env_checker import check_env

from irrivise_core.agents.ppo import CheckpointError, PPOPolicy, load_verified, train_ppo
from irrivise_core.config import load_training
from irrivise_core.crops import aquacrop_adapter
from irrivise_core.envs.features import N_FEATURES
from irrivise_core.envs.irrigation_env import IrrigationEnv
from irrivise_core.evaluation.experiment import ExperimentConfig, run_experiment
from irrivise_core.evaluation.runner import run_episode
from irrivise_core.evaluation.stats import bootstrap_ci, paired_difference


def test_env_passes_checker_and_is_reproducible(scenario, train, forecaster):
    env = IrrigationEnv(scenario, train, forecaster, seed=0)
    check_env(env)

    def rollout(seed):
        e = IrrigationEnv(scenario, train, forecaster, seed=seed)
        obs, info = e.reset(seed=seed)
        total, done, steps = 0.0, False, 0
        while not done:
            obs, r, done, trunc, info = e.step(steps % 5)
            assert e.observation_space.contains(obs) and np.isfinite(r) and not trunc
            total += r
            steps += 1
        with pytest.raises(RuntimeError):
            e.step(0)  # no action after termination
        return total, steps, info

    a, b = rollout(3), rollout(3)
    assert a[0] == b[0] and a[1] == scenario.crop.season_length
    assert "yield_ratio_proxy" in a[2] and a[2]["water_used_mm"] <= env.base_scenario.seasonal_budget_mm * 1.5 + 1e-9


def test_env_enforces_budget_and_penalises_infeasible_requests(scenario, train, forecaster):
    sc = scenario.model_copy(update={"seasonal_budget_mm": 30.0})
    env = IrrigationEnv(sc, train, forecaster, randomize=False, seed=1)
    env.reset(seed=1)
    infos = [env.step(4)[4] for _ in range(5)]
    assert sum(i["applied_mm"] for i in infos) == pytest.approx(30.0)
    assert infos[-1]["applied_mm"] == 0 and infos[-1]["reward_violation"] < 0


@pytest.fixture(scope="module")
def tiny_model(tmp_path_factory, scenario, train, split, seasons, forecaster):
    val = [s for s in seasons if s.season_id in split.validation][:2]
    cfg = load_training("cpu_quick").model_copy(update={"total_timesteps": 512, "eval_freq_steps": 256,
                                                        "hyperparameters": load_training("cpu_quick").hyperparameters.model_copy(update={"n_steps": 256})})
    out = tmp_path_factory.mktemp("models")
    return train_ppo(scenario, cfg, train[:3], val, forecaster, out, "m1", 7, "checksum"), out


def test_ppo_trains_saves_reloads_and_infers(tiny_model, scenario, seasons, forecaster):
    trained, out = tiny_model
    m = trained.manifest
    assert m["actual_timesteps"] >= 512 and m["checkpoint_sha256"] and m["test_seasons_used"] == []
    assert m["history"] and m["final_validation"]["episodes"] == 2 and m["research_quality"] is False
    model, manifest = load_verified(out, "m1")
    policy = PPOPolicy(model, manifest, scenario)
    r = run_episode(scenario, seasons[-1], forecaster, 1, "carat_full", ppo_policy=policy)
    assert r.summary["max_daily_violations"] == 0 and len(r.daily) == scenario.crop.season_length
    assert all(d["initial_action_mm"] in scenario.actions_mm for d in r.daily)


def test_tampered_or_incompatible_checkpoint_rejected(tiny_model, tmp_path):
    _, out = tiny_model
    copy = tmp_path / "models"
    shutil.copytree(out, copy)
    with (copy / "m1.zip").open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(CheckpointError, match="hash mismatch"):
        load_verified(copy, "m1")
    shutil.copy(out / "m1.zip", copy / "m1.zip")
    manifest = json.loads((copy / "m1.json").read_text())
    manifest["feature_spec_version"] = "old"
    (copy / "m1.json").write_text(json.dumps(manifest))
    with pytest.raises(CheckpointError, match="Incompatible"):
        load_verified(copy, "m1")
    with pytest.raises(CheckpointError):
        load_verified(copy, "../m1")
    assert N_FEATURES == manifest["n_features"]


def test_matched_experiment_with_baselines_and_stats(scenario, seasons, split, forecaster):
    test = [s for s in seasons if s.season_id in split.test][:2]
    cfg = ExperimentConfig(methods=["fixed_schedule", "soil_threshold", "lookahead_carat"], reference_method="fixed_schedule", seeds=[1, 2, 3])
    out = run_experiment(cfg, scenario, test, forecaster)
    assert out["n_runs"] == 18 and out["n_failed"] == 0 and out["hard_constraint_violations"] == 0
    cells = {m: sorted((r["season_id"], r["seed"]) for r in out["rows"] if r["method"] == m) for m in cfg.methods}
    assert cells["fixed_schedule"] == cells["soil_threshold"] == cells["lookahead_carat"]
    comp = out["paired_vs_reference"]["soil_threshold"]
    assert comp["seasonal_irrigation_mm"]["n_pairs"] == 6 and comp["seasonal_irrigation_mm"]["ci95"] is not None
    assert any("simulated" in line for line in out["narrative"])
    with pytest.raises(ValueError, match="trained PPO"):
        run_experiment(ExperimentConfig(methods=["ppo", "fixed_schedule"], seeds=[1]), scenario, test, forecaster)
    with pytest.raises(ValueError, match="No test seasons"):
        run_experiment(cfg, scenario, [], forecaster)


def test_paired_statistics():
    assert bootstrap_ci([1.0, 2.0]) is None
    lo, hi = bootstrap_ci(np.arange(10.0))
    assert lo < 4.5 < hi
    d = paired_difference([2, 3, 4, 5, 6, 7], [1, 1, 1, 1, 1, 1], higher_is_better=True)
    assert d["mean_difference"] == pytest.approx(3.5) and d["status"].startswith("better")
    small = paired_difference([1, 2], [0, 0], higher_is_better=True)
    assert "insufficient" in small["status"]


@pytest.mark.skipif(not aquacrop_adapter.available()[0], reason="aquacrop not installed")
def test_aquacrop_rainfed_vs_irrigated(frame):
    rainfed = aquacrop_adapter.evaluate_schedule(frame, "2010-06-15", [0.0] * 140)
    irrigated = aquacrop_adapter.evaluate_schedule(frame, "2010-06-15", [10.0 if d % 3 == 0 else 0.0 for d in range(140)])
    assert rainfed["aquacrop_seasonal_irrigation_mm"] == 0
    assert 0 < irrigated["aquacrop_seasonal_irrigation_mm"] <= 470
    assert 0 <= rainfed["aquacrop_simulated_dry_yield_t_ha"] <= irrigated["aquacrop_simulated_dry_yield_t_ha"] < 30
    with pytest.raises(ValueError):
        aquacrop_adapter.evaluate_schedule(frame, "2010-06-15", [-1.0] * 140)
