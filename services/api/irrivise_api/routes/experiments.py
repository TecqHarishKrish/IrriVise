"""Matched benchmark experiments."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Query
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from irrivise_core.baselines.policies import METHODS
from irrivise_core.evaluation.experiment import ExperimentConfig

from ..db.models import ExperimentGroup, Job, ModelRecord, new_id
from ..db.session import get_session
from ..errors import ApiError, not_found
from ..schemas import ExperimentIn
from ..services import artifacts, datasets, jobs
from ..services.scenarios import build_config, get_scenario
from .simulations import _coerce

router = APIRouter(tags=["experiments"])


def experiment_dict(g: ExperimentGroup, session: Session, full: bool = False) -> dict:
    job = session.get(Job, g.job_id) if g.job_id else None
    out = {"id": g.id, "name": g.name, "scenario_id": g.scenario_id, "model_id": g.model_id, "status": job.status if job else g.status,
           "job_id": g.job_id, "progress": job.progress if job else None, "error": job.error if job else None,
           "config": json.loads(g.config_json), "created_at": g.created_at.isoformat() + "Z"}
    summary = json.loads(g.summary_json) if g.summary_json else None
    if summary:
        out["n_runs"], out["n_failed"] = summary["n_runs"], summary["n_failed"]
        if full:
            out["summary"] = summary
            manifest = artifacts.experiment_dir(g.id) / "manifest.json"
            out["manifest"] = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else None
    return out


@router.post("/experiments", status_code=202)
def enqueue(body: ExperimentIn, idempotency_key: str | None = Header(default=None, max_length=100), session: Session = Depends(get_session)):
    scenario = get_scenario(session, body.scenario_id)
    cfg = build_config(scenario)
    data = body.model_dump()
    scenario_id, model_id = data.pop("scenario_id"), data.pop("model_id")
    try:
        config = ExperimentConfig(**data)
    except ValidationError as exc:
        raise ApiError(422, "validation_error", "Invalid experiment configuration", json.loads(exc.json(include_url=False))) from exc
    if config.reference_method not in config.methods:
        raise ApiError(422, "validation_error", "The reference method must be one of the selected methods")
    if any(METHODS[m].needs_model for m in config.methods):
        if not model_id:
            raise ApiError(422, "model_required", "Selected PPO-based methods need a trained model (model_id)")
        if not session.get(ModelRecord, model_id):
            raise not_found("Model")
    if not scenario.dataset_id:
        raise ApiError(422, "scenario_incomplete", "Attach a weather dataset first")
    d = datasets.get_dataset(session, scenario.dataset_id)
    seasons, _, split = datasets.seasons_for(d, scenario.planting_mmdd, cfg.crop.season_length)
    eval_ids = split.ids(config.split)
    if not eval_ids:
        raise ApiError(422, "no_evaluation_seasons", f"No {config.split} seasons ({split.rule}); evaluation never falls back to training seasons")
    runs = config.cells([s for s in seasons if s.season_id in eval_ids]) * len(config.methods)
    if runs > config.max_runs:
        raise ApiError(422, "too_many_runs", f"{runs} runs exceed the cap of {config.max_runs}")
    group = ExperimentGroup(id=new_id(), scenario_id=scenario_id, model_id=model_id, name=config.name, config_json=config.model_dump_json())
    session.add(group)
    session.flush()
    job, _ = jobs.enqueue(session, "experiment", {"experiment_id": group.id, "config": config.model_dump(), "model_id": model_id},
                          scenario.project_id, scenario.id, idempotency_key, total_steps=runs)
    group.job_id = job.id
    out = experiment_dict(group, session)
    out["planned_runs"] = runs
    out["evaluation_seasons"] = list(eval_ids)
    return out


@router.get("/experiments")
def list_experiments(scenario_id: str | None = None, session: Session = Depends(get_session)):
    query = select(ExperimentGroup).order_by(ExperimentGroup.created_at.desc()).limit(200)
    if scenario_id:
        query = query.where(ExperimentGroup.scenario_id == scenario_id)
    return [experiment_dict(g, session) for g in session.scalars(query).all()]


def _group(session: Session, experiment_id: str) -> ExperimentGroup:
    g = session.get(ExperimentGroup, experiment_id)
    if not g:
        raise not_found("Experiment")
    return g


@router.get("/experiments/{experiment_id}")
def read_experiment(experiment_id: str, session: Session = Depends(get_session)):
    return experiment_dict(_group(session, experiment_id), session, full=True)


@router.get("/experiments/{experiment_id}/results")
def results(experiment_id: str, offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=5000), session: Session = Depends(get_session)):
    g = _group(session, experiment_id)
    path = artifacts.experiment_dir(g.id) / "results.csv"
    if not path.exists():
        raise ApiError(409, "not_ready", "Experiment results are not available yet")
    rows = [_coerce(r) for r in artifacts.read_csv(path)]
    summary = json.loads(g.summary_json or "{}")
    return {"experiment_id": g.id, "total": len(rows), "rows": rows[offset:offset + limit],
            "paired_vs_reference": summary.get("paired_vs_reference"), "table": summary.get("table"), "narrative": summary.get("narrative")}
