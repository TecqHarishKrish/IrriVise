"""Non-PPO sensor-fault bench: runs methods that need no trained model.

usage: python faultbench.py <label> <split> <scenario-overrides-json> [modes] [seeds]
Writes <label>.json next to this script: per (mode, bias, method) means + per-run rows.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path("/home/claude/irrivise")
sys.path.insert(0, str(ROOT / "packages/irrivise_core"))

from irrivise_core.config import default_scenario  # noqa: E402
from irrivise_core.data.weather import chronological_split, extract_seasons, read_weather_csv  # noqa: E402
from irrivise_core.evaluation.runner import run_episode  # noqa: E402
from irrivise_core.simulation.forecast import ClimatologyForecaster  # noqa: E402

label, split_name, overrides = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
modes = sys.argv[4].split(",") if len(sys.argv) > 4 else ["nominal", "missing", "biased+", "biased-", "stuck"]
seeds = [int(s) for s in sys.argv[5].split(",")] if len(sys.argv) > 5 else [1, 2, 3, 4, 5]
METHODS = ["fixed_schedule", "soil_threshold", "lookahead_carat"]

base = default_scenario(**{"carat": {"observation_cost": 0.0}, **overrides})
frame, _ = read_weather_csv(ROOT / "data/sample/synthetic_weather_tn_v1.csv")
seasons, _ = extract_seasons(frame, base.planting_mmdd, base.crop.season_length)
split = chronological_split([s.season_id for s in seasons])
forecaster = ClimatologyForecaster([s for s in seasons if s.season_id in split.train])
evaluation = [s for s in seasons if s.season_id in split.ids(split_name)]

out, t0 = {"label": label, "split": split_name, "overrides": overrides, "seeds": seeds, "cells": {}}, time.time()
for mode in modes:
    sensor_mode, bias = mode, base.sensor.bias_m3m3
    if mode.startswith("biased"):
        sensor_mode, bias = "biased", (0.03 if mode.endswith("+") else -0.03)
    sensor = base.sensor.model_copy(update={"mode": sensor_mode, "bias_m3m3": bias, "noise_std_m3m3": 0.02})
    scenario = base.model_copy(update={"observation_budget": 10, "sensor": sensor})
    for method in METHODS:
        rows = []
        for season in evaluation:
            for seed in seeds:
                r = run_episode(scenario, season, forecaster, seed, method, record_states=False, carat_diagnostics=False)
                s = r.summary
                rows.append({"season": season.season_id, "seed": seed, "yield": s["yield_proxy_t_ha"], "water": s["seasonal_irrigation_mm"],
                             "stress": s["cumulative_stress"], "reads": s["observation_count"], "rmse": s["twin_rmse_mm"],
                             "bias": s.get("twin_bias_mm"), "reward": s["objective_with_observation_cost"]})
        mean = {k: round(float(np.mean([r[k] for r in rows])), 3) for k in ["yield", "water", "stress", "reads", "rmse", "bias", "reward"]}
        out["cells"][f"{mode}|{method}"] = {"mean": mean, "rows": rows}
        print(f"{mode:9s} {method:16s} " + " ".join(f"{k}={v}" for k, v in mean.items()), flush=True)
print(f"elapsed {time.time() - t0:.0f}s")
Path(__file__).with_name(f"{label}.json").write_text(json.dumps(out))
