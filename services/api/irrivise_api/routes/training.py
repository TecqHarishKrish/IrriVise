"""PPO training jobs and model metadata."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from irrivise_core.config import load_training
from irrivise_core.config.schemas import PPOHyperparameters, TrainingConfig

from ..db.models import ModelRecord
from ..db.session import get_session
from ..errors import ApiError, not_found
from ..schemas import TrainingIn
from ..services import artifacts, datasets, jobs
from ..services.scenarios import build_config, get_scenario

router = APIRouter(tags=["training"])


def model_dict(m: ModelRecord, with_manifest: bool = False) -> dict:
    out = {"id": m.id, "job_id": m.job_id, "scenario_id": m.scenario_id, "dataset_id": m.dataset_id, "algorithm": m.algorithm, "preset": m.preset,
           "seed": m.seed, "actual_timesteps": m.actual_timesteps, "checkpoint_sha256": m.checkpoint_sha256, "config_sha256": m.config_sha256,
           "validation": json.loads(m.validation_json), "selected": m.selected, "research_quality": m.research_quality, "status": m.status,
           "created_at": m.created_at.isoformat() + "Z"}
    if with_manifest:
        path = artifacts.safe_join(*m.manifest_path.split("/"))
        out["manifest"] = json.loads(path.read_text()) if path.exists() else None
        checkpoint = artifacts.safe_join(*m.checkpoint_path.split("/"))
        out["checkpoint_bytes"] = checkpoint.stat().st_size if checkpoint.exists() else None
    return out


@router.post("/training", status_code=202)
def enqueue(body: TrainingIn, idempotency_key: str | None = Header(default=None, max_length=100), session: Session = Depends(get_session)):
    scenario = get_scenario(session, body.scenario_id)
    cfg = build_config(scenario)
    if not scenario.dataset_id:
        raise ApiError(422, "scenario_incomplete", "Attach a weather dataset before training")
    preset = load_training(body.preset)
    if body.preset != "cpu_quick" and not body.confirm_long_run:
        raise ApiError(422, "confirmation_required", f"Preset {body.preset} can take a long time on CPU; set confirm_long_run to proceed")
    try:
        hp = PPOHyperparameters(**{**preset.hyperparameters.model_dump(), **(body.hyperparameters or {})})
        config = TrainingConfig(**{**preset.model_dump(), "hyperparameters": hp, "total_timesteps": body.total_timesteps or preset.total_timesteps,
                                   "seeds": tuple(body.seeds or preset.seeds)})
    except ValidationError as exc:
        raise ApiError(422, "validation_error", "Invalid training configuration", json.loads(exc.json(include_url=False))) from exc
    if body.preset == "cpu_quick" and config.total_timesteps > 10_000:
        raise ApiError(422, "validation_error", "Quick smoke preset is limited to 10,000 timesteps")
    d = datasets.get_dataset(session, scenario.dataset_id)
    seasons, _, split = datasets.seasons_for(d, scenario.planting_mmdd, cfg.crop.season_length)
    if not split.train:
        raise ApiError(422, "no_training_seasons", f"No training seasons available ({split.rule})")
    payload = body.model_dump()
    job, _ = jobs.enqueue(session, "training", payload, scenario.project_id, scenario.id, idempotency_key,
                          total_steps=config.total_timesteps * len(config.seeds))
    out = jobs.job_dict(job)
    out["resolved_config"] = config.model_dump(mode="json")
    out["split"] = split.as_dict()
    return out


@router.get("/models")
def list_models(scenario_id: str | None = None, session: Session = Depends(get_session)):
    query = select(ModelRecord).order_by(ModelRecord.created_at.desc())
    if scenario_id:
        query = query.where(ModelRecord.scenario_id == scenario_id)
    return [model_dict(m) for m in session.scalars(query).all()]


@router.get("/models/{model_id}")
def read_model(model_id: str, session: Session = Depends(get_session)):
    m = session.get(ModelRecord, model_id)
    if not m:
        raise not_found("Model")
    return model_dict(m, with_manifest=True)
