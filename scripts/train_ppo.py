"""Train PPO from the command line on a dataset's TRAINING seasons (validation selects the checkpoint).

    python scripts/train_ppo.py --preset cpu_quick --dataset sample --seed 42

Writes artifacts/models/<id>.zip + <id>.json (manifest with SHA-256). The quick
preset is a functional smoke test only, not research-quality training.
"""
import argparse
import json
import uuid

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

from irrivise_core.agents.ppo import train_ppo
from irrivise_core.config import default_scenario, load_training
from irrivise_core.data.weather import chronological_split, extract_seasons, read_weather_csv
from irrivise_core.simulation.forecast import ClimatologyForecaster
from irrivise_core.util.repro import sha256_file

DATASETS = {"sample": ROOT / "data" / "sample" / "synthetic_weather_tn_v1.csv"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=["cpu_quick", "cpu_standard", "cpu_research"], default="cpu_quick")
    parser.add_argument("--dataset", default="sample", help="'sample' or a path to a validated weather CSV")
    parser.add_argument("--seed", type=int, action="append", help="repeatable; defaults to the preset seeds")
    parser.add_argument("--timesteps", type=int, help="override preset total timesteps")
    args = parser.parse_args()
    path = DATASETS.get(args.dataset) or ROOT / args.dataset
    frame, _ = read_weather_csv(path)
    scenario = default_scenario()
    seasons, _ = extract_seasons(frame, scenario.planting_mmdd, scenario.crop.season_length)
    split = chronological_split([s.season_id for s in seasons])
    train = [s for s in seasons if s.season_id in split.train]
    val = [s for s in seasons if s.season_id in split.validation]
    config = load_training(args.preset)
    update = {}
    if args.seed:
        update["seeds"] = tuple(args.seed)
    if args.timesteps:
        update["total_timesteps"] = args.timesteps
        update["eval_freq_steps"] = max(256, min(config.eval_freq_steps, args.timesteps // 2))
    config = config.model_copy(update=update)
    print(f"split: {split.rule}; train={list(split.train)} validation={list(split.validation)} (test untouched: {list(split.test)})")
    for seed in config.seeds:
        model_id = str(uuid.uuid4())
        trained = train_ppo(scenario, config, train, val, ClimatologyForecaster(train), ROOT / "artifacts" / "models", model_id, seed,
                            sha256_file(path), progress=lambda p: print(json.dumps({k: v for k, v in p.items() if k != "point"})) if "metric_name" in p else None)
        m = trained.manifest
        print(json.dumps({k: m[k] for k in ("model_id", "seed", "actual_timesteps", "stop_reason", "checkpoint_sha256", "best_validation_mean_reward",
                                            "final_validation", "research_quality")}, indent=2))


if __name__ == "__main__":
    main()
