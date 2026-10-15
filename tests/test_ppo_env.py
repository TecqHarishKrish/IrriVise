from pathlib import Path
import numpy as np
from stable_baselines3.common.env_checker import check_env
from irrivise_core.data import load_weather
from irrivise_core.ppo_env import IrrigationEnv


def test_gym_env_contract_and_budget():
    weather = load_weather(Path(__file__).resolve().parents[1] / "data/sample/weather.csv")
    env = IrrigationEnv(weather, budget_mm=0)
    check_env(env)
    first, _ = env.reset(seed=42)
    second, _ = env.reset(seed=42)
    assert np.array_equal(first, second)
    done = False
    while not done:
        observation, reward, done, truncated, info = env.step(4)
        assert info["applied_mm"] == 0
        assert env.observation_space.contains(observation)
        assert np.isfinite(reward)
        assert not truncated
