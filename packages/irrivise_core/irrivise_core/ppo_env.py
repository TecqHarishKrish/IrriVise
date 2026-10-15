"""Gymnasium environment for CPU smoke training on the fast surrogate.

The policy observation contains the estimated state and a past-based forecast.
The reward is calculated after applying an action to a hidden simulated state.
"""
from __future__ import annotations

from math import sqrt
import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .science import Soil, Weather, feasible_action, water_step


class IrrigationEnv(gym.Env):
    metadata = {"render_modes": []}
    ACTIONS_MM = (0.0, 5.0, 10.0, 15.0, 20.0)

    def __init__(self, weather: list[Weather], budget_mm: float = 350, daily_max_mm: float = 20):
        super().__init__()
        if not weather or budget_mm < 0 or daily_max_mm < 0:
            raise ValueError("Invalid environment configuration")
        self.weather = weather
        self.soil = Soil()
        self.budget_mm = budget_mm
        self.daily_max_mm = daily_max_mm
        self.action_space = spaces.Discrete(len(self.ACTIONS_MM))
        self.observation_space = spaces.Box(low=0, high=1, shape=(7,), dtype=np.float32)
        self.day = 0
        self.truth = 0.0
        self.estimate = 0.0
        self.variance = 64.0
        self.water_used = 0.0
        self.previous_rain = 0.0
        self.stress_sum = 0.0

    def _observation(self) -> np.ndarray:
        minimum = self.soil.mm(self.soil.wilting)
        maximum = self.soil.mm(self.soil.saturation)
        return np.array([
            (self.estimate - minimum) / (maximum - minimum),
            min(1.0, sqrt(self.variance) / 30),
            self.day / len(self.weather),
            min(1.0, self.previous_rain / 40),
            min(1.0, self.previous_rain * 0.6 / 40),
            min(1.0, 4.5 / 12),
            (self.budget_mm - self.water_used) / self.budget_mm if self.budget_mm else 0,
        ], dtype=np.float32)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self.day = 0
        self.truth = self.soil.mm(self.soil.field_capacity * 0.85)
        self.estimate = self.soil.mm(self.soil.field_capacity * 0.82)
        self.variance = 64.0
        self.water_used = 0.0
        self.previous_rain = 0.0
        self.stress_sum = 0.0
        return self._observation(), {"source": "synthetic demonstration"}

    def step(self, action: int):
        if self.day >= len(self.weather):
            raise RuntimeError("Episode already terminated")
        if not self.action_space.contains(action):
            raise ValueError("Invalid discrete irrigation action")
        proposed = self.ACTIONS_MM[int(action)]
        applied = feasible_action(proposed, self.daily_max_mm, self.budget_mm - self.water_used)
        actual = self.weather[self.day]
        forecast_rain = self.previous_rain * 0.6
        predicted = water_step(self.estimate, forecast_rain, applied, 4.5, self.soil)
        self.estimate = predicted.next_storage_mm
        self.variance = min(400, self.variance + 9)
        realized = water_step(self.truth, actual.rain_mm, applied, actual.eto_mm, self.soil)
        self.truth = realized.next_storage_mm
        self.previous_rain = actual.rain_mm
        self.water_used += applied
        self.stress_sum += realized.stress
        self.day += 1
        terminated = self.day == len(self.weather)
        reward = -0.2 * (applied / 20) - realized.stress
        if terminated:
            reward += 5 * max(0, 1 - self.stress_sum / len(self.weather))
        info = {"proposed_mm": proposed, "applied_mm": applied, "stress_proxy": realized.stress, "reward_water": -0.2 * applied / 20, "reward_stress": -realized.stress}
        return self._observation(), float(reward), terminated, False, info
