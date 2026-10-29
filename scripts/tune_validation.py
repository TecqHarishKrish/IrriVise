"""Tune observation-policy parameters on VALIDATION seasons only (never test).

    python scripts/tune_validation.py --model-root artifacts/models --model-id <id> [--out docs/results/tuning.json]

Grid:
* CARAT (full method): observation_cost ∈ {0.0, 0.01, 0.03, 0.06}
* B5 uncertainty threshold (std/TAW) ∈ {0.04, 0.06, 0.08, 0.12}
Selection criterion: highest mean `objective_with_observation_cost` over
validation seasons × seeds (ties → fewer readings). The chosen values are
then fixed before any test-season experiment is run.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

from irrivise_core.agents.ppo import PPOPolicy, load_verified
from irrivise_core.config import default_scenario
from irrivise_core.data.weather import chronological_split, extract_seasons, read_weather_csv
from irrivise_core.evaluation.runner import run_episode
from irrivise_core.simulation.forecast import ClimatologyForecaster

COSTS = (0.0, 0.01, 0.03, 0.06)
THRESHOLDS = (0.04, 0.06, 0.08, 0.12)
SEEDS = (101, 102, 103)


def score(rows: list[dict]) -> dict:
    return {"mean_objective": float(np.mean([r["objective_with_observation_cost"] for r in rows])),
            "mean_readings": float(np.mean([r["observation_count"] for r in rows])),
            "mean_irrigation_mm": float(np.mean([r["seasonal_irrigation_mm"] for r in rows])),
            "mean_yield_proxy_t_ha": float(np.mean([r["yield_proxy_t_ha"] for r in rows])), "n": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", default="artifacts/models")
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--out", default="docs/results/validation_tuning.json")
    args = parser.parse_args()
    frame, _ = read_weather_csv(ROOT / "data/sample/synthetic_weather_tn_v1.csv")
    base = default_scenario()
    seasons, _ = extract_seasons(frame, base.planting_mmdd, base.crop.season_length)
    split = chronological_split([s.season_id for s in seasons])
    forecaster = ClimatologyForecaster([s for s in seasons if s.season_id in split.train])
    validation = [s for s in seasons if s.season_id in split.validation]
    model, manifest = load_verified((ROOT / args.model_root).resolve(), args.model_id)
    results = {"carat_observation_cost": {}, "b5_uncertainty_threshold": {}}
    for cost in COSTS:
        sc = base.model_copy(update={"carat": base.carat.model_copy(update={"observation_cost": cost})})
        policy = PPOPolicy(model, manifest, sc)
        rows = [run_episode(sc, s, forecaster, seed, "carat_full", ppo_policy=policy, record_states=False).summary for s in validation for seed in SEEDS]
        results["carat_observation_cost"][str(cost)] = score(rows)
        print("cost", cost, results["carat_observation_cost"][str(cost)])
    policy = PPOPolicy(model, manifest, base)
    for threshold in THRESHOLDS:
        rows = [run_episode(base, s, forecaster, seed, "ppo_uncertainty", ppo_policy=policy, uncertainty_threshold=threshold, record_states=False).summary
                for s in validation for seed in SEEDS]
        results["b5_uncertainty_threshold"][str(threshold)] = score(rows)
        print("threshold", threshold, results["b5_uncertainty_threshold"][str(threshold)])
    pick = lambda table: max(table, key=lambda k: (round(table[k]["mean_objective"], 6), -table[k]["mean_readings"]))  # noqa: E731
    out = {"created_at": datetime.now(timezone.utc).isoformat(), "split": split.as_dict(), "validation_seasons": [s.season_id for s in validation],
           "seeds": SEEDS, "model_id": args.model_id, "model_checkpoint_sha256": manifest["checkpoint_sha256"],
           "criterion": "max mean objective_with_observation_cost on validation seasons (test seasons untouched)",
           "results": results, "selected": {"carat_observation_cost": float(pick(results["carat_observation_cost"])),
                                            "b5_uncertainty_threshold": float(pick(results["b5_uncertainty_threshold"]))}}
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out["selected"]))


if __name__ == "__main__":
    main()
