"""Gymnasium environment: one episode = one growing season on the fast surrogate.

Action space: Discrete(len(actions_mm)) → [0, 5, 10, 15, 20] mm/day by default.
Observation: Box(0, 1, (16,)) — see features.FEATURES (twin estimates, past
observed weather, forecast, budgets). Hard water limits are enforced by
projection (logged as proposed vs applied) and penalised via λ_v.

Observation regime during training: readings arrive at random days with a
random per-episode budget so the policy experiences both fresh and stale
beliefs. The policy does not choose when to observe; CARAT or a baseline
observation policy does that at evaluation time.
"""
from __future__ import annotations

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from ..carat.risk import hard_project
from ..config.schemas import ScenarioConfig
from ..data.weather import Season
from ..simulation.forecast import ClimatologyForecaster
from ..simulation.world import FieldWorld
from .features import N_FEATURES, agent_features
from .reward import daily_reward, terminal_reward


def randomized_scenario(base: ScenarioConfig, rng: np.random.Generator) -> ScenarioConfig:
    """Controlled domain randomisation within physically valid ranges."""
    sensor = base.sensor.model_copy(update={"noise_std_m3m3": float(rng.choice([0.01, 0.02, 0.04]))})
    unc = base.uncertainty.model_copy(update={"initial_fraction_mean": float(rng.uniform(0.4, 0.95))})
    return base.model_copy(update={
        "seasonal_budget_mm": float(base.seasonal_budget_mm * rng.uniform(0.5, 1.5)),
        "observation_budget": int(rng.integers(0, 41)),
        "sensor": sensor, "uncertainty": unc,
    })


class IrrigationEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, scenario: ScenarioConfig, seasons: list[Season], forecaster: ClimatologyForecaster,
                 randomize: bool = True, observation_regime: str = "random", seed: int | None = None):
        super().__init__()
        if not seasons:
            raise ValueError("At least one training season is required")
        if observation_regime not in {"random", "none"}:
            raise ValueError("observation_regime must be random or none")
        self.base_scenario = scenario
        self.seasons = seasons
        self.forecaster = forecaster
        self.randomize = randomize
        self.observation_regime = observation_regime
        self.actions_mm = np.asarray(scenario.actions_mm, dtype=float)
        self.action_space = spaces.Discrete(len(self.actions_mm))
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(N_FEATURES,), dtype=np.float32)
        self.world: FieldWorld | None = None
        self.scenario = scenario
        self._episode_rng = np.random.default_rng(seed)
        self._obs_rng = np.random.default_rng(seed)

    def _observe_if_scheduled(self) -> None:
        world = self.world
        if self.observation_regime == "none" or world.sensor.remaining <= 0 or world.done:
            return
        rate = self.scenario.observation_budget / max(1, world.length)
        if self._obs_rng.random() < rate:
            world.observe(correct=True)

    def _obs(self) -> np.ndarray:
        return agent_features(self.world.view(), self.scenario.soil.theta_wp, self.scenario.soil.theta_sat)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._episode_rng = np.random.default_rng(seed)
            self._obs_rng = np.random.default_rng(seed + 1)
        options = options or {}
        index = options.get("season_index")
        if index is None:
            index = int(self._episode_rng.integers(len(self.seasons)))
        if not 0 <= index < len(self.seasons):
            raise ValueError("season_index out of range")
        self.scenario = randomized_scenario(self.base_scenario, self._episode_rng) if self.randomize else self.base_scenario
        world_seed = int(options.get("world_seed", self._episode_rng.integers(2**31)))
        self.world = FieldWorld(self.scenario, self.seasons[index], self.forecaster, world_seed)
        self._observe_if_scheduled()
        return self._obs(), {"season_id": self.seasons[index].season_id, "world_seed": world_seed, "source": "simulated"}

    def step(self, action):
        if self.world is None or self.world.done:
            raise RuntimeError("Call reset(): episode has terminated")
        if not self.action_space.contains(int(action)):
            raise ValueError("Invalid discrete irrigation action")
        world = self.world
        day = world.day
        proposed = float(self.actions_mm[int(action)])
        applied, status = hard_project(proposed, self.scenario.daily_max_mm, world.remaining_water_mm)
        farm = world.apply(applied)
        parts = daily_reward(self.scenario, day, proposed, applied, farm.ks)
        reward = parts["reward"]
        terminated = world.done
        info = {"day": day, "proposed_mm": proposed, "applied_mm": applied, "constraint_status": status, **parts}
        if terminated:
            ratio = world.yield_ratio()
            bonus = terminal_reward(self.scenario, ratio)
            reward += bonus
            info.update({"terminal_yield_reward": bonus, "yield_ratio_proxy": ratio, "water_used_mm": world.water_used_mm})
            obs = np.zeros(N_FEATURES, dtype=np.float32)
        else:
            self._observe_if_scheduled()
            obs = self._obs()
        return obs, float(reward), terminated, False, info
