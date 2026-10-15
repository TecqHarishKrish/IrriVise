"""Quick functional PPO training; this is not research-grade model selection."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
sys.path.insert(0, str(ROOT / "packages/irrivise_core"))

from irrivise_core.data import checksum, load_weather
from irrivise_core.ppo_env import IrrigationEnv
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", choices=["cpu_quick"], default="cpu_quick")
    parser.add_argument("--dataset", choices=["sample"], default="sample")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timesteps", type=int, default=2048)
    args = parser.parse_args()
    if not 256 <= args.timesteps <= 10000:
        parser.error("Quick smoke timesteps must be between 256 and 10000")
    path = ROOT / "data/sample/weather.csv"
    weather = load_weather(path)
    env = IrrigationEnv(weather)
    check_env(env)
    model = PPO("MlpPolicy", env, seed=args.seed, n_steps=256, batch_size=64, learning_rate=3e-4, device="cpu", verbose=0)
    model.learn(total_timesteps=args.timesteps)
    output = ROOT / "artifacts/models" / f"ppo-sample-seed-{args.seed}"
    output.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(output))
    restored = PPO.load(str(output) + ".zip", env=env, device="cpu")
    observation, _ = env.reset(seed=args.seed)
    action, _ = restored.predict(observation, deterministic=True)
    observation, reward, terminated, truncated, info = env.step(int(action))
    manifest = {"algorithm": "PPO", "preset": args.preset, "dataset": "synthetic demonstration", "dataset_sha256": checksum(path), "seed": args.seed, "requested_timesteps": args.timesteps, "actual_timesteps": model.num_timesteps, "checkpoint": str(output.relative_to(ROOT)) + ".zip", "inference_action_mm": info["applied_mm"], "inference_reward": reward, "research_quality": False, "evaluation": "save/load/one-step inference only"}
    (output.parent / f"ppo-sample-seed-{args.seed}.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
