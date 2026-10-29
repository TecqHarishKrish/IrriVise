"""Sensor-fault bench for the twin's bias handling, using methods that need no PPO model.

    python scripts/sensor_bias_bench.py --split test --out docs/results/sensor_bias_nonppo
    python scripts/sensor_bias_bench.py --split validation --prior 0.015 --drift 0.003 --bias-methods augmented

Runs every (sensor fault × twin_bias method × planner) cell on the chosen split with
budget 10, noise 0.02 m³/m³ and carat.observation_cost 0 (the tuned setting used in
the benchmarks). Faults: nominal, missing (25 % dropout), biased+ (+0.03 m³/m³),
biased- (−0.03), stuck (from day 40). Planners that correct the twin from readings
and need no trained model: ``soil_threshold`` (B1, fixed-interval readings) and
``lookahead_carat`` (CARAT planner, VOI readings); ``fixed_schedule`` (B0) is the
information-free reference. Paired differences vs ``twin_bias.method = none`` use
a bootstrap over matched (season, seed) cells. Writes <out>.json and <out>.md.
All outcomes are simulated.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

from irrivise_core.config import default_scenario
from irrivise_core.data.weather import chronological_split, extract_seasons, read_weather_csv
from irrivise_core.evaluation.runner import run_episode
from irrivise_core.simulation.forecast import ClimatologyForecaster
from irrivise_core.util.repro import code_revision, sha256_file

FAULTS = {"nominal": ("nominal", 0.03), "missing": ("missing", 0.03), "biased+": ("biased", 0.03), "biased-": ("biased", -0.03),
          "stuck": ("stuck", 0.03)}
PLANNERS = ["fixed_schedule", "soil_threshold", "lookahead_carat"]
METRICS = {"yield_proxy_t_ha": "Yield proxy (t/ha)", "seasonal_irrigation_mm": "Irrigation (mm)", "cumulative_stress": "Σ(1−Ks)",
           "observation_count": "Readings", "twin_rmse_mm": "Twin RMSE (mm)", "twin_bias_mm": "Twin bias (mm)",
           "objective_with_observation_cost": "Objective"}
LABEL = {"none": "no bias handling", "innovation_monitor": "innovation monitor", "augmented": "augmented offset state"}


def bootstrap(d: np.ndarray, rng: np.random.Generator, n: int = 4000) -> tuple[float, float, float]:
    means = d[rng.integers(0, len(d), (n, len(d)))].mean(axis=1)
    return float(d.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["validation", "test"], default="test")
    ap.add_argument("--seeds", default="1,2,3,4,5")
    ap.add_argument("--bias-methods", default="none,innovation_monitor,augmented")
    ap.add_argument("--prior", type=float, help="override twin_bias.prior_std_m3m3")
    ap.add_argument("--drift", type=float, help="override twin_bias.drift_std_m3m3")
    ap.add_argument("--out", help="output path without extension (default: print only)")
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(",")]
    bias_methods = args.bias_methods.split(",")
    twin_overrides = {k: v for k, v in (("prior_std_m3m3", args.prior), ("drift_std_m3m3", args.drift)) if v is not None}

    dataset = ROOT / "data/sample/synthetic_weather_tn_v1.csv"
    base = default_scenario(carat={"observation_cost": 0.0})
    frame, _ = read_weather_csv(dataset)
    seasons, _ = extract_seasons(frame, base.planting_mmdd, base.crop.season_length)
    split = chronological_split([s.season_id for s in seasons])
    forecaster = ClimatologyForecaster([s for s in seasons if s.season_id in split.train])
    evaluation = [s for s in seasons if s.season_id in split.ids(args.split)]

    started, cells = time.monotonic(), {}
    for fault, (mode, bias) in FAULTS.items():
        sensor = base.sensor.model_copy(update={"mode": mode, "bias_m3m3": bias, "noise_std_m3m3": 0.02})
        for bm in bias_methods:
            twin_bias = base.twin_bias.model_copy(update={"method": bm, **twin_overrides})
            scenario = base.model_copy(update={"observation_budget": 10, "sensor": sensor, "twin_bias": twin_bias})
            for planner in PLANNERS:
                if planner == "fixed_schedule" and bm != bias_methods[0]:
                    continue  # takes no readings: identical under every bias method
                rows = []
                for season in evaluation:
                    for seed in seeds:
                        s = run_episode(scenario, season, forecaster, seed, planner, record_states=False, carat_diagnostics=False).summary
                        rows.append({"season_id": season.season_id, "seed": seed, **{m: float(s[m]) for m in METRICS}})
                cells[f"{fault}|{bm}|{planner}"] = rows
                print(f"{fault:8s} {bm:18s} {planner:16s} yield={np.mean([r['yield_proxy_t_ha'] for r in rows]):.3f}", flush=True)

    rng = np.random.default_rng(0)
    summary, paired = {}, {}
    for key, rows in cells.items():
        summary[key] = {m: round(float(np.mean([r[m] for r in rows])), 4) for m in METRICS}
        fault, bm, planner = key.split("|")
        ref = cells.get(f"{fault}|none|{planner}")
        if ref is not None and bm != "none":
            for m in ("yield_proxy_t_ha", "seasonal_irrigation_mm", "objective_with_observation_cost"):
                d = np.array([a[m] - b[m] for a, b in zip(rows, ref)])
                paired.setdefault(key, {})[m] = [round(v, 4) for v in bootstrap(d, rng)]
    elapsed = time.monotonic() - started
    print(f"{len(cells)} cells, {sum(len(r) for r in cells.values())} runs, {elapsed:.0f} s")
    if not args.out:
        return

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"split": args.split, "seasons": [s.season_id for s in evaluation], "seeds": seeds, "observation_budget": 10,
                "sensor_noise_m3m3": 0.02, "carat_observation_cost": 0.0, "twin_bias": base.twin_bias.model_copy(update=twin_overrides).model_dump(),
                "dataset_sha256": sha256_file(dataset), "code_revision": code_revision(), "label": "SIMULATED — not field data"}
    out.with_suffix(".json").write_text(json.dumps({"manifest": manifest, "summary": summary, "paired_vs_none": paired, "rows": cells}, indent=1), encoding="utf-8")

    lines = [f"## Twin sensor-bias handling, no-PPO planners ({args.split} seasons)", "",
             f"Seasons {manifest['seasons']} × seeds {seeds} = {len(evaluation) * len(seeds)} matched cells per row · budget 10 · noise 0.02 m³/m³ · "
             f"augmented prior σ_b = {manifest['twin_bias']['prior_std_m3m3']}, drift {manifest['twin_bias']['drift_std_m3m3']} m³/m³/day · "
             "generated by `scripts/sensor_bias_bench.py`. All outcomes are simulated.", "",
             "| Fault | Planner | Twin bias handling | " + " | ".join(METRICS.values()) + " |", "|" + "---|" * (3 + len(METRICS))]
    for key, s in summary.items():
        fault, bm, planner = key.split("|")
        name = "— (no readings)" if planner == "fixed_schedule" else LABEL[bm]
        lines.append(f"| {fault} | {planner} | {name} | " + " | ".join(f"{s[m]:.2f}" if m != "observation_count" else f"{s[m]:.1f}" for m in METRICS) + " |")
    lines += ["", "Paired differences vs no bias handling (same planner, fault, season and seed), mean [bootstrap 95 % CI]:", "",
              "| Fault | Planner | Handling | Δ yield proxy (t/ha) | Δ irrigation (mm) | Δ objective |", "|---|---|---|---|---|---|"]
    for key, d in paired.items():
        fault, bm, planner = key.split("|")
        fmt = lambda v, p: f"{v[0]:+.{p}f} [{v[1]:+.{p}f}, {v[2]:+.{p}f}]" + (" *" if v[1] > 0 or v[2] < 0 else "")  # noqa: E731
        lines.append(f"| {fault} | {planner} | {LABEL[bm]} | {fmt(d['yield_proxy_t_ha'], 3)} | {fmt(d['seasonal_irrigation_mm'], 1)} | "
                     f"{fmt(d['objective_with_observation_cost'], 2)} |")
    lines += ["", "\\* 95 % CI excludes 0."]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out.with_suffix('.md')} and .json")


if __name__ == "__main__":
    main()
