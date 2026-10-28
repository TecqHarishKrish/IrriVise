"""Run a matched benchmark from a YAML config without the web UI.

    python scripts/run_experiment.py --config configs/experiments/baselines.yaml [--model-id <id>]

PPO-based methods need a trained checkpoint in artifacts/models (train with
scripts/train_ppo.py). Without --model-id the most recent verified manifest is
used. Outputs go to artifacts/experiments/cli-<UTC timestamp>/ (results.csv,
summary.json, manifest.json); earlier outputs are never overwritten.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

import yaml

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

from irrivise_core.agents.ppo import PPOPolicy, load_verified
from irrivise_core.baselines.policies import METHODS
from irrivise_core.config import default_scenario
from irrivise_core.data.weather import chronological_split, extract_seasons, read_weather_csv
from irrivise_core.evaluation.experiment import ExperimentConfig, run_experiment
from irrivise_core.simulation.forecast import ClimatologyForecaster
from irrivise_core.util.repro import code_revision, package_versions, sha256_file, sha256_json

MODELS = ROOT / "artifacts" / "models"


def latest_model(models: Path = MODELS) -> str | None:
    manifests = sorted(models.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return manifests[0].stem if manifests else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--model-id")
    parser.add_argument("--model-root", default="artifacts/models", help="directory holding <id>.zip/<id>.json")
    parser.add_argument("--no-aquacrop", action="store_true", help="skip AquaCrop even if the config enables it")
    args = parser.parse_args()
    models = (ROOT / args.model_root).resolve()
    spec = yaml.safe_load((ROOT / args.config).read_text())
    dataset = ROOT / spec.pop("dataset", "data/sample/synthetic_weather_tn_v1.csv")
    scenario = default_scenario(**spec.pop("scenario", {}))
    config = ExperimentConfig(**spec)
    frame, _ = read_weather_csv(dataset)
    seasons, _ = extract_seasons(frame, scenario.planting_mmdd, scenario.crop.season_length)
    split = chronological_split([s.season_id for s in seasons])
    forecaster = ClimatologyForecaster([s for s in seasons if s.season_id in split.train])
    evaluation = [s for s in seasons if s.season_id in split.ids(config.split)]
    factory, model_manifest = None, None
    if any(METHODS[m].needs_model for m in config.methods):
        model_id = args.model_id or latest_model(models)
        if not model_id:
            raise SystemExit("PPO methods selected but no model found: run scripts/train_ppo.py first")
        model, model_manifest = load_verified(models, model_id)
        factory = lambda cfg: PPOPolicy(model, model_manifest, cfg)  # noqa: E731
    print(f"{config.name}: {len(config.methods)} methods × {config.cells(evaluation)} cells on {config.split} seasons {[s.season_id for s in evaluation]}")
    aquacrop_fn = None
    if config.aquacrop and not args.no_aquacrop:
        from irrivise_core.crops.aquacrop_adapter import evaluate_schedule
        aquacrop_fn = lambda season, schedule: evaluate_schedule(frame, season.start, schedule)  # noqa: E731
    summary = run_experiment(config, scenario, evaluation, forecaster, factory, aquacrop_fn,
                             progress=lambda d, n, msg: print(f"[{d}/{n}] {msg}") if d % 10 == 0 or d == n else None)
    out = ROOT / "artifacts" / "experiments" / f"cli-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out.mkdir(parents=True, exist_ok=False)
    rows = summary.pop("rows")
    import csv
    with (out / "results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({k for r in rows for k in r}), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    manifest = {"config_file": args.config, "config": config.model_dump(), "scenario_sha256": sha256_json(scenario.model_dump(mode="json")),
                "dataset": str(dataset.relative_to(ROOT)), "dataset_sha256": sha256_file(dataset), "split": split.as_dict(),
                "model_id": model_manifest["model_id"] if model_manifest else None,
                "model_checkpoint_sha256": model_manifest["checkpoint_sha256"] if model_manifest else None,
                "code_revision": code_revision(), "package_versions": package_versions(),
                "files": {n: sha256_file(out / n) for n in ("results.csv", "summary.json")}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("\n".join(summary["narrative"]))
    print(f"\nSaved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
