"""Job handlers executed inside a worker child process (never inside API requests)."""
from __future__ import annotations

import json
import os
import time
from datetime import date

from sqlalchemy import select

from irrivise_core.agents.ppo import CheckpointError, PPOPolicy, TrainingCancelled, load_verified, train_ppo
from irrivise_core.baselines.policies import METHODS
from irrivise_core.config import load_training
from irrivise_core.config.schemas import PPOHyperparameters, TrainingConfig
from irrivise_core.crops import aquacrop_adapter
from irrivise_core.data import nasa_power
from irrivise_core.evaluation.experiment import ExperimentConfig, run_experiment
from irrivise_core.evaluation.runner import run_episode
from irrivise_core.util.repro import code_revision, package_versions, sha256_file, sha256_json

from ..db.models import ExperimentGroup, Job, ModelRecord, SimulationRun, WeatherDataset, new_id, utcnow
from ..db.session import session_scope
from ..services import artifacts, datasets, jobs
from ..services.scenarios import build_config, get_scenario


class JobCancelled(Exception):
    pass


class SupervisorLost(Exception):
    """The supervising worker process died; the child stops instead of running orphaned."""


class JobContext:
    """Progress/heartbeat/cancellation helper bound to one job id."""

    def __init__(self, job_id: str, parent_pid: int | None = None):
        self.job_id = job_id
        self.parent_pid = parent_pid
        self._last_write = 0.0
        self._last_cancel_check = 0.0
        self._cancel = False

    def progress(self, phase: str, current: int | None = None, total: int | None = None, message: str = "",
                 metric_name: str | None = None, metric_value: float | None = None, data: dict | None = None, force: bool = False) -> None:
        now = time.monotonic()
        if not force and metric_name is None and now - self._last_write < 1.0:
            return
        self._last_write = now
        with session_scope() as s:
            job = s.get(Job, self.job_id)
            job.phase = phase[:120]
            if current is not None:
                job.current_step = int(current)
            if total is not None:
                job.total_steps = int(total)
            if job.total_steps:
                job.progress = min(99.0, 100.0 * job.current_step / job.total_steps)
            job.heartbeat_at = utcnow()
            self._cancel = job.cancel_requested
            jobs.add_event(s, job, phase, message, metric_name, metric_value, data)

    def cancelled(self) -> bool:
        if self.parent_pid is not None and os.getppid() != self.parent_pid:
            raise SupervisorLost("Worker supervisor exited while the job was running")
        now = time.monotonic()
        if now - self._last_cancel_check > 1.0:
            self._last_cancel_check = now
            with session_scope() as s:
                job = s.get(Job, self.job_id)
                job.heartbeat_at = utcnow()
                self._cancel = job.cancel_requested
        return self._cancel

    def check(self) -> None:
        if self.cancelled():
            raise JobCancelled()


def _manifest_base() -> dict:
    return {"code_revision": code_revision(), "package_versions": package_versions(), "created_at": utcnow().isoformat() + "Z"}


def _scenario_context(s, scenario_id: str):
    scenario = get_scenario(s, scenario_id)
    cfg = build_config(scenario)
    if not scenario.dataset_id:
        raise ValueError("Scenario has no weather dataset attached")
    dataset = datasets.get_dataset(s, scenario.dataset_id)
    seasons, skipped, split = datasets.seasons_for(dataset, scenario.planting_mmdd, cfg.crop.season_length)
    return scenario, cfg, dataset, seasons, split


def _policy_factory(s, model_id: str | None, scenario_id: str):
    if not model_id:
        return None, None
    record = s.get(ModelRecord, model_id)
    if not record or record.status != "ready":
        raise CheckpointError("Model not found or not ready; train a PPO model first")
    model, manifest = load_verified(artifacts.model_dir(), model_id)
    return (lambda cfg: PPOPolicy(model, manifest, cfg)), manifest


# -- handlers ---------------------------------------------------------------------

def handle_weather(ctx: JobContext, payload: dict) -> dict:
    ctx.progress("contacting NASA POWER", 0, 3, force=True)
    root = artifacts.safe_join()
    manifest = nasa_power.download_power(payload["latitude"], payload["longitude"], date.fromisoformat(payload["start"]),
                                         date.fromisoformat(payload["end"]), payload["time_standard"], root)
    ctx.check()
    ctx.progress("registering dataset", 2, 3, force=True)
    with session_scope() as s:
        existing = s.scalar(select(WeatherDataset).where(WeatherDataset.checksum_sha256 == manifest["checksum_sha256"],
                                                         WeatherDataset.archived.is_(False)))
        if existing:
            return {"dataset_id": existing.id, "cache_hit": True, "rows": existing.rows}
        record = WeatherDataset(id=new_id(), name=payload.get("name", "NASA POWER daily"), source="nasa_power", file_path=manifest["processed_path"],
                                checksum_sha256=manifest["checksum_sha256"], rows=manifest["rows"], start_date=manifest["start"],
                                end_date=manifest["end"], latitude=payload["latitude"], longitude=payload["longitude"],
                                time_standard=f"NASA POWER {manifest['time_standard']}", units_json=json.dumps(manifest["native_units"]),
                                validation_json=json.dumps(manifest["validation"]),
                                provenance_json=json.dumps({k: v for k, v in manifest.items() if k not in {"validation"}}), license=nasa_power.LICENSE)
        s.add(record)
        s.flush()
        return {"dataset_id": record.id, "cache_hit": manifest["cache_hit"], "rows": manifest["rows"]}


def handle_simulation(ctx: JobContext, payload: dict) -> dict:
    ctx.progress("preparing scenario", 0, 4, force=True)
    with session_scope() as s:
        scenario, cfg, dataset, seasons, split = _scenario_context(s, payload["scenario_id"])
        factory, model_manifest = _policy_factory(s, payload.get("model_id"), scenario.id)
        dataset_id, dataset_checksum, dataset_path, soil_profile = dataset.id, dataset.checksum_sha256, dataset.file_path, scenario.soil_profile
        frame = datasets.load_frame(dataset)
    if not seasons:
        raise ValueError("The scenario's dataset has no complete season for this planting date")
    season_id = payload.get("season_id") or (split.test[0] if split.test else seasons[-1].season_id)
    season = next((x for x in seasons if x.season_id == season_id), None)
    if season is None:
        raise ValueError(f"Season {season_id} is not available in the dataset")
    which = "train" if season_id in split.train else "validation" if season_id in split.validation else "test"
    forecaster = datasets.forecaster_for(seasons, split)
    method = METHODS[payload["method"]]
    policy = factory(cfg) if factory else None
    ctx.progress(f"simulating season {season_id} with {method.code}", 1, 4, force=True)
    result = run_episode(cfg, season, forecaster, payload["seed"], method.key, ppo_policy=policy, record_states=True)
    ctx.check()
    aquacrop = None
    if payload.get("aquacrop", True):
        ctx.progress("AquaCrop evaluation of the applied schedule", 2, 4, force=True)
        try:
            aquacrop = aquacrop_adapter.evaluate_schedule(frame, season.start, [d["applied_mm"] for d in result.daily], soil_profile)
        except Exception as exc:  # recorded, not hidden
            aquacrop = {"error": f"{type(exc).__name__}: {exc}"[:400]}
    ctx.check()
    ctx.progress("writing artifacts", 3, 4, force=True)
    run_id = new_id()
    directory = artifacts.run_dir(run_id)
    artifacts.write_csv(directory / "daily.csv", result.daily)
    artifacts.write_json(directory / "decisions.json", result.decisions)
    artifacts.write_csv(directory / "evaluation_truth.csv", result.truth)
    summary = {**result.summary, "aquacrop": aquacrop}
    artifacts.write_json(directory / "summary.json", summary)
    manifest = {**_manifest_base(), "run_id": run_id, "kind": "simulation", "method": method.as_dict(), "season_id": season_id, "split": which,
                "split_rule": split.rule, "seed": payload["seed"], "scenario_id": scenario.id, "scenario_config": cfg.model_dump(mode="json"),
                "scenario_sha256": sha256_json(cfg.model_dump(mode="json")), "dataset_id": dataset_id, "dataset_path": dataset_path,
                "weather_dataset_checksum": dataset_checksum, "model_id": payload.get("model_id"),
                "model_checkpoint_sha256": model_manifest["checkpoint_sha256"] if model_manifest else None,
                "forecast_training_seasons": list(forecaster.training_ids),
                "hidden_parameters_evaluation_only": result.hidden_parameters,
                "files": {name: sha256_file(directory / name) for name in ("daily.csv", "decisions.json", "evaluation_truth.csv", "summary.json")},
                "labels": {"truth": "evaluation_truth.csv is the hidden simulated reference — post-run evaluation only",
                           "yield": "yield_proxy_t_ha is an FAO-33 proxy; aquacrop block is AquaCrop-simulated; neither is measured"}}
    artifacts.write_json(directory / "manifest.json", manifest)
    with session_scope() as s:
        s.add(SimulationRun(id=run_id, job_id=ctx.job_id, scenario_id=scenario.id, dataset_id=dataset_id, season_id=season_id, split=which,
                            method=method.key, model_id=payload.get("model_id"), seed=payload["seed"], config_sha256=manifest["scenario_sha256"],
                            artifact_dir=artifacts.relative(directory), summary_json=json.dumps(summary), aquacrop_json=json.dumps(aquacrop)))
    return {"run_id": run_id, "season_id": season_id, "split": which}


def handle_training(ctx: JobContext, payload: dict) -> dict:
    preset = load_training(payload["preset"])
    update = {}
    if payload.get("total_timesteps"):
        update["total_timesteps"] = payload["total_timesteps"]
        update["eval_freq_steps"] = max(256, min(preset.eval_freq_steps, payload["total_timesteps"] // 2))
    if payload.get("seeds"):
        update["seeds"] = tuple(payload["seeds"])
    if payload.get("hyperparameters"):
        update["hyperparameters"] = PPOHyperparameters(**{**preset.hyperparameters.model_dump(), **payload["hyperparameters"]})
    config = TrainingConfig(**{**preset.model_dump(), **update})
    with session_scope() as s:
        scenario, cfg, dataset, seasons, split = _scenario_context(s, payload["scenario_id"])
        dataset_id, checksum = dataset.id, dataset.checksum_sha256
    train = [x for x in seasons if x.season_id in split.train]
    val = [x for x in seasons if x.season_id in split.validation]
    if not train:
        raise ValueError(f"No training seasons available ({split.rule}); import a longer dataset")
    forecaster = datasets.forecaster_for(seasons, split)
    total = config.total_timesteps * len(config.seeds)
    ctx.progress("training started", 0, total, f"{len(train)} train / {len(val)} validation seasons; test seasons untouched", force=True,
                 data={"split": split.as_dict(), "config": config.model_dump(mode="json")})
    models = []
    for i, seed in enumerate(config.seeds):
        model_id = new_id()

        def progress(info: dict, offset=i * config.total_timesteps) -> None:
            ctx.progress(info["phase"], info["current_step"], total, metric_name=info.get("metric_name"),
                         metric_value=info.get("metric_value"), data=info.get("point"))

        try:
            trained = train_ppo(cfg, config, train, val, forecaster, artifacts.model_dir(), model_id, seed, checksum, progress=progress,
                                cancelled=ctx.cancelled, step_offset=i * config.total_timesteps, total_for_progress=total)
        except TrainingCancelled as exc:
            raise JobCancelled(str(exc)) from exc
        m = trained.manifest
        with session_scope() as s:
            s.add(ModelRecord(id=model_id, job_id=ctx.job_id, scenario_id=scenario.id, dataset_id=dataset_id, preset=config.preset, seed=seed,
                              actual_timesteps=m["actual_timesteps"], checkpoint_path=artifacts.relative(trained.checkpoint_path),
                              checkpoint_sha256=m["checkpoint_sha256"], manifest_path=artifacts.relative(trained.manifest_path),
                              config_sha256=m["training_config_sha256"], validation_json=json.dumps(m.get("final_validation") or {}),
                              research_quality=bool(m["research_quality"])))
        models.append((model_id, (m.get("final_validation") or {}).get("mean_reward")))
    scored = [m for m in models if m[1] is not None]
    selected = max(scored, key=lambda m: m[1])[0] if scored else models[-1][0]
    with session_scope() as s:
        s.get(ModelRecord, selected).selected = True
    return {"model_ids": [m[0] for m in models], "selected_model_id": selected,
            "selection": "highest validation mean reward across seeds" if scored else "no validation seasons: last seed"}


def handle_experiment(ctx: JobContext, payload: dict) -> dict:
    with session_scope() as s:
        group = s.get(ExperimentGroup, payload["experiment_id"])
        scenario, cfg, dataset, seasons, split = _scenario_context(s, group.scenario_id)
        factory, model_manifest = _policy_factory(s, group.model_id, scenario.id)
        config = ExperimentConfig(**json.loads(group.config_json))
        dataset_id, checksum, soil_profile = dataset.id, dataset.checksum_sha256, scenario.soil_profile
        frame = datasets.load_frame(dataset)
        group.status = "running"
    eval_seasons = [x for x in seasons if x.season_id in split.ids(config.split)]
    forecaster = datasets.forecaster_for(seasons, split)
    aq = (lambda season, schedule: aquacrop_adapter.evaluate_schedule(frame, season.start, schedule, soil_profile)) if config.aquacrop else None
    total = config.cells(eval_seasons) * len(config.methods)
    ctx.progress("experiment started", 0, total, force=True)
    try:
        summary = run_experiment(config, cfg, eval_seasons, forecaster, factory, aq,
                                 progress=lambda done, n, msg: ctx.progress("running matched cells", done, n, msg),
                                 cancelled=ctx.cancelled)
    except InterruptedError as exc:
        raise JobCancelled(str(exc)) from exc
    directory = artifacts.experiment_dir(group.id)
    rows = summary.pop("rows")
    artifacts.write_csv(directory / "results.csv", rows)
    artifacts.write_json(directory / "summary.json", summary)
    manifest = {**_manifest_base(), "experiment_id": group.id, "config": config.model_dump(), "scenario_config": cfg.model_dump(mode="json"),
                "scenario_sha256": sha256_json(cfg.model_dump(mode="json")), "dataset_id": dataset_id, "weather_dataset_checksum": checksum,
                "split": config.split, "split_rule": split.rule, "evaluation_seasons": [x.season_id for x in eval_seasons],
                "forecast_training_seasons": list(forecaster.training_ids), "model_id": group.model_id,
                "model_checkpoint_sha256": model_manifest["checkpoint_sha256"] if model_manifest else None,
                "files": {n: sha256_file(directory / n) for n in ("results.csv", "summary.json")},
                "matching": "identical (season, seed, observation budget, sensor noise) cells and common random numbers for all methods"}
    artifacts.write_json(directory / "manifest.json", manifest)
    with session_scope() as s:
        group = s.get(ExperimentGroup, payload["experiment_id"])
        group.status = "succeeded"
        group.artifact_dir = artifacts.relative(directory)
        group.summary_json = json.dumps(summary)
    return {"experiment_id": payload["experiment_id"], "n_runs": summary["n_runs"], "n_failed": summary["n_failed"], "results_csv_rows": len(rows)}


HANDLERS = {"weather_fetch": handle_weather, "simulation": handle_simulation, "training": handle_training, "experiment": handle_experiment}


def execute(job_id: str, parent_pid: int | None = None) -> None:
    """Entry point of a worker child process: run one claimed job to a terminal state."""
    import logging
    import traceback

    from ..db.session import dispose_all

    dispose_all()  # never reuse a parent's connections after spawn/fork
    ctx = JobContext(job_id, parent_pid)
    with session_scope() as s:
        job = s.get(Job, job_id)
        kind, payload = job.kind, json.loads(job.payload_json)
    try:
        result = HANDLERS[kind](ctx, payload)
        with session_scope() as s:
            job = s.get(Job, job_id)
            job.result_json = json.dumps(result, default=str)
            jobs.transition(s, job, "succeeded", "completed", message="Artifacts persisted and validated")
    except SupervisorLost as exc:
        with session_scope() as s:
            job = s.get(Job, job_id)
            if job.status == "running":
                jobs.transition(s, job, "interrupted", "interrupted", error=f"{exc}; partial artifacts are not used. Re-queue to run again.")
            _mark_experiment(s, payload, "interrupted")
    except JobCancelled as exc:
        with session_scope() as s:
            job = s.get(Job, job_id)
            jobs.transition(s, job, "cancelled", "cancelled", message=f"Cancelled cooperatively. {exc}"[:400])
            _mark_experiment(s, payload, "cancelled")
    except Exception as exc:  # failure is recorded with diagnostics, never hidden
        logging.getLogger("irrivise.worker").error("job %s failed\n%s", job_id, traceback.format_exc())
        with session_scope() as s:
            job = s.get(Job, job_id)
            jobs.transition(s, job, "failed", "failed", error=f"{type(exc).__name__}: {exc}", message=f"{type(exc).__name__}: {exc}"[:400])
            _mark_experiment(s, payload, "failed")


def _mark_experiment(s, payload: dict, status: str) -> None:
    if "experiment_id" in payload:
        group = s.get(ExperimentGroup, payload["experiment_id"])
        if group:
            group.status = status
