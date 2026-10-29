"""Stable-Baselines3 PPO training, verified checkpoints and inference.

* Training uses TRAINING seasons only; periodic deterministic evaluation on
  VALIDATION seasons selects the best checkpoint. Test seasons are never used.
* Every checkpoint gets a manifest with SHA-256, configuration hash, dataset
  checksum, feature-spec version and package versions. Loading verifies the
  hash and compatibility and only reads files under the controlled model root.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from ..config.schemas import ScenarioConfig, TrainingConfig
from ..data.weather import Season
from ..envs.features import FEATURE_SPEC_VERSION, N_FEATURES, agent_features
from ..envs.irrigation_env import IrrigationEnv
from ..simulation.forecast import ClimatologyForecaster
from ..simulation.world import AgentView
from ..util.repro import package_versions, sha256_file, sha256_json

ProgressFn = Callable[[dict], None]
CancelFn = Callable[[], bool]


class TrainingCancelled(Exception):
    pass


class TrainingDiverged(FloatingPointError):
    pass


class CheckpointError(ValueError):
    pass


def evaluate_policy_on_seasons(model, scenario: ScenarioConfig, seasons: list[Season], forecaster: ClimatologyForecaster,
                               world_seed: int = 1000) -> dict:
    """Deterministic evaluation (no randomisation, no readings) on the given seasons."""
    env = IrrigationEnv(scenario, seasons, forecaster, randomize=False, observation_regime="none")
    rewards, yields, water = [], [], []
    for index in range(len(seasons)):
        obs, _ = env.reset(seed=world_seed + index, options={"season_index": index, "world_seed": world_seed + index})
        total, done, info = 0.0, False, {}
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, _, info = env.step(int(action))
            total += reward
        rewards.append(total)
        yields.append(info["yield_ratio_proxy"])
        water.append(info["water_used_mm"])
    return {"mean_reward": float(np.mean(rewards)), "std_reward": float(np.std(rewards)), "mean_yield_ratio_proxy": float(np.mean(yields)),
            "mean_irrigation_mm": float(np.mean(water)), "episodes": len(seasons)}


@dataclass
class TrainedModel:
    model_id: str
    seed: int
    checkpoint_path: Path
    manifest_path: Path
    manifest: dict


def train_ppo(scenario: ScenarioConfig, config: TrainingConfig, train_seasons: list[Season], validation_seasons: list[Season],
              forecaster: ClimatologyForecaster, output_dir: Path, model_id: str, seed: int, dataset_checksum: str,
              progress: ProgressFn | None = None, cancelled: CancelFn | None = None, step_offset: int = 0,
              total_for_progress: int | None = None) -> TrainedModel:
    import torch
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.env_checker import check_env
    from stable_baselines3.common.utils import set_random_seed

    if not train_seasons:
        raise ValueError("Training requires at least one training season")
    set_random_seed(seed)
    torch.set_num_threads(1)
    output_dir.mkdir(parents=True, exist_ok=True)
    env = IrrigationEnv(scenario, train_seasons, forecaster, randomize=config.domain_randomization, seed=seed)
    check_env(IrrigationEnv(scenario, train_seasons, forecaster, randomize=config.domain_randomization, seed=seed), warn=True)
    hp = config.hyperparameters
    model = PPO("MlpPolicy", env, learning_rate=hp.learning_rate, n_steps=hp.n_steps, batch_size=hp.batch_size, n_epochs=hp.n_epochs,
                gamma=hp.gamma, gae_lambda=hp.gae_lambda, clip_range=hp.clip_range, ent_coef=hp.ent_coef, vf_coef=hp.vf_coef,
                max_grad_norm=hp.max_grad_norm, policy_kwargs={"net_arch": list(hp.net_arch)}, seed=seed, device="cpu", verbose=0)
    best_path = output_dir / f"{model_id}.zip"
    eval_seasons = validation_seasons or []
    history: list[dict] = []
    started = time.monotonic()
    total = total_for_progress or config.total_timesteps

    class Monitor(BaseCallback):
        def __init__(self):
            super().__init__()
            self.best = -math.inf
            self.no_improve = 0
            self.episode_rewards: list[float] = []
            self.current = 0.0
            self.stop_reason: str | None = None

        def _on_step(self) -> bool:
            for reward, done in zip(self.locals["rewards"], self.locals["dones"]):
                self.current += float(reward)
                if done:
                    self.episode_rewards.append(self.current)
                    self.current = 0.0
            if cancelled and self.num_timesteps % 256 == 0 and cancelled():
                self.stop_reason = "cancelled"
                return False
            if time.monotonic() - started > config.max_wall_seconds:
                self.stop_reason = "wall_time_cap"
                return False
            if self.num_timesteps % config.eval_freq_steps == 0 or self.num_timesteps == config.total_timesteps:
                for p in self.model.policy.parameters():
                    if not torch.all(torch.isfinite(p)):
                        raise TrainingDiverged("Non-finite policy parameters; training halted")
                point = {"timesteps": self.num_timesteps, "train_mean_episode_reward": float(np.mean(self.episode_rewards[-10:])) if self.episode_rewards else None,
                         "wall_seconds": round(time.monotonic() - started, 2)}
                if eval_seasons:
                    metrics = evaluate_policy_on_seasons(self.model, scenario, eval_seasons, forecaster)
                    point.update({f"validation_{k}": v for k, v in metrics.items()})
                    score = metrics["mean_reward"]
                    if score > self.best:
                        self.best = score
                        self.no_improve = 0
                        self.model.save(str(best_path))
                        point["checkpoint_saved"] = True
                    else:
                        self.no_improve += 1
                else:
                    self.model.save(str(best_path))
                    point["checkpoint_saved"] = True
                history.append(point)
                if progress:
                    progress({"phase": f"training seed {seed}", "current_step": step_offset + self.num_timesteps, "total_steps": total,
                              "metric_name": "validation_mean_reward" if eval_seasons else "train_mean_episode_reward",
                              "metric_value": point.get("validation_mean_reward", point["train_mean_episode_reward"]), "point": point})
                if config.early_stop_evals and self.no_improve >= config.early_stop_evals:
                    self.stop_reason = "early_stopping"
                    return False
            elif progress and self.num_timesteps % 512 == 0:
                progress({"phase": f"training seed {seed}", "current_step": step_offset + self.num_timesteps, "total_steps": total})
            return True

    monitor = Monitor()
    model.learn(total_timesteps=config.total_timesteps, callback=monitor, progress_bar=False)
    if monitor.stop_reason == "cancelled":
        raise TrainingCancelled(f"Training cancelled at {model.num_timesteps} steps")
    if not best_path.exists():
        model.save(str(best_path))
    # Verify: reload the selected checkpoint and run inference on a fresh episode.
    restored = PPO.load(str(best_path), device="cpu")
    probe = IrrigationEnv(scenario, train_seasons, forecaster, randomize=False, observation_regime="none")
    obs, _ = probe.reset(seed=seed, options={"season_index": 0, "world_seed": seed})
    action, _ = restored.predict(obs, deterministic=True)
    if not probe.action_space.contains(int(action)):
        raise CheckpointError("Restored model produced an invalid action")
    final_validation = evaluate_policy_on_seasons(restored, scenario, eval_seasons, forecaster) if eval_seasons else None
    manifest = {
        "model_id": model_id, "algorithm": "PPO", "policy": "MlpPolicy", "seed": seed, "preset": config.preset,
        "requested_timesteps": config.total_timesteps, "actual_timesteps": int(model.num_timesteps), "stop_reason": monitor.stop_reason or "completed",
        "feature_spec_version": FEATURE_SPEC_VERSION, "n_features": N_FEATURES, "actions_mm": list(scenario.actions_mm),
        "training_config": config.model_dump(mode="json"), "training_config_sha256": sha256_json(config.model_dump(mode="json")),
        "scenario_sha256": sha256_json(scenario.model_dump(mode="json")), "dataset_checksum_sha256": dataset_checksum,
        "train_seasons": [s.season_id for s in train_seasons], "validation_seasons": [s.season_id for s in eval_seasons],
        "test_seasons_used": [], "checkpoint_file": best_path.name, "checkpoint_sha256": sha256_file(best_path),
        "checkpoint_bytes": best_path.stat().st_size, "selection": "best validation mean reward" if eval_seasons else "final (no validation seasons)",
        "best_validation_mean_reward": None if monitor.best == -math.inf else monitor.best, "final_validation": final_validation,
        "history": history, "inference_check": {"action_index": int(action), "action_mm": float(scenario.actions_mm[int(action)])},
        "wall_seconds": round(time.monotonic() - started, 2), "package_versions": package_versions(),
        "research_quality": config.preset != "cpu_quick" and config.total_timesteps >= 100_000,
        "label": "Trained on simulated seasons from the fast surrogate; not field-validated",
    }
    manifest_path = output_dir / f"{model_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return TrainedModel(model_id, seed, best_path, manifest_path, manifest)


def load_verified(model_root: Path, model_id: str) -> tuple[object, dict]:
    """Load a checkpoint only from the controlled root after hash/compatibility checks."""
    from stable_baselines3 import PPO

    if not model_id.replace("-", "").isalnum() or len(model_id) > 80:
        raise CheckpointError("Invalid model id")
    root = model_root.resolve()
    manifest_path = (root / f"{model_id}.json").resolve()
    if root not in manifest_path.parents or not manifest_path.is_file():
        raise CheckpointError("Model manifest not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checkpoint = (root / manifest["checkpoint_file"]).resolve()
    if root not in checkpoint.parents or not checkpoint.is_file():
        raise CheckpointError("Checkpoint file missing")
    if sha256_file(checkpoint) != manifest["checkpoint_sha256"]:
        raise CheckpointError("Checkpoint hash mismatch: file was modified or corrupted")
    if manifest.get("feature_spec_version") != FEATURE_SPEC_VERSION or manifest.get("n_features") != N_FEATURES:
        raise CheckpointError(f"Incompatible checkpoint (feature spec {manifest.get('feature_spec_version')}); retrain with the current code")
    model = PPO.load(str(checkpoint), device="cpu")
    if model.observation_space.shape != (N_FEATURES,):
        raise CheckpointError("Checkpoint observation space does not match")
    return model, manifest


class PPOPolicy:
    name = "ppo"

    def __init__(self, model, manifest: dict, scenario: ScenarioConfig):
        if list(manifest.get("actions_mm", [])) != list(scenario.actions_mm):
            raise CheckpointError("Checkpoint action grid differs from the scenario action grid")
        self.model = model
        self.manifest = manifest
        self.scenario = scenario

    def propose(self, view: AgentView) -> float:
        obs = agent_features(view, self.scenario.soil.theta_wp, self.scenario.soil.theta_sat)
        action, _ = self.model.predict(obs, deterministic=True)
        return float(self.scenario.actions_mm[int(action)])
