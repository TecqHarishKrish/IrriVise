"""Projects/scenarios ↔ typed ScenarioConfig."""
from __future__ import annotations

import json

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from irrivise_core.config import load_carat, load_crop, load_soil
from irrivise_core.config.schemas import (CaratConfig, RewardWeights, RiskConfig, ScenarioConfig, SensorConfig, UncertaintyConfig)
from irrivise_core.util.repro import sha256_json

from ..db.models import Project, Scenario, new_id
from ..errors import ApiError, not_found
from . import datasets

ADVANCED_SECTIONS = {"carat": CaratConfig, "risk": RiskConfig, "reward": RewardWeights, "uncertainty": UncertaintyConfig}


def build_config(s: Scenario) -> ScenarioConfig:
    advanced = json.loads(s.config_json or "{}")
    try:
        crop, soil = load_crop(s.crop_profile), load_soil(s.soil_profile)
        sections = {}
        for key, model in ADVANCED_SECTIONS.items():
            base = load_carat("default").model_dump() if key == "carat" else model().model_dump()
            if key == "uncertainty":
                base["initial_fraction_mean"] = s.initial_fraction_mean
            base.update(advanced.get(key, {}))
            sections[key] = model(**base)
        return ScenarioConfig(crop=crop, soil=soil, planting_mmdd=s.planting_mmdd, daily_max_mm=s.daily_max_mm,
                              seasonal_budget_mm=s.seasonal_budget_mm, observation_budget=s.observation_budget,
                              sensor=SensorConfig(noise_std_m3m3=s.sensor_noise_m3m3, mode=s.sensor_mode), **sections)
    except (ValidationError, ValueError) as exc:
        details = exc.errors(include_url=False) if isinstance(exc, ValidationError) else str(exc)
        raise ApiError(422, "invalid_scenario", f"Scenario configuration is invalid: {exc}".splitlines()[0][:300], json.loads(json.dumps(details, default=str)))


def validate_advanced(advanced: dict) -> dict:
    unknown = set(advanced) - set(ADVANCED_SECTIONS)
    if unknown:
        raise ApiError(422, "invalid_scenario", f"Unknown advanced section(s): {sorted(unknown)}")
    for key, value in advanced.items():
        if not isinstance(value, dict):
            raise ApiError(422, "invalid_scenario", f"Advanced section '{key}' must be an object")
    return advanced


def scenario_dict(s: Scenario, include_config: bool = True) -> dict:
    out = {c: getattr(s, c) for c in ("id", "project_id", "name", "latitude", "longitude", "crop_profile", "soil_profile", "planting_mmdd",
                                       "daily_max_mm", "seasonal_budget_mm", "observation_budget", "sensor_noise_m3m3", "sensor_mode",
                                       "initial_fraction_mean", "dataset_id", "validation_status", "archived")}
    out["validation_messages"] = json.loads(s.validation_messages or "[]")
    out["advanced"] = json.loads(s.config_json or "{}")
    out["created_at"] = s.created_at.isoformat() + "Z"
    out["updated_at"] = s.updated_at.isoformat() + "Z"
    if include_config:
        try:
            cfg = build_config(s)
            out["season_length_days"] = cfg.crop.season_length
            out["scenario_sha256"] = sha256_json(cfg.model_dump(mode="json"))
            out["resolved_config"] = cfg.model_dump(mode="json")
        except ApiError as exc:
            out["season_length_days"] = None
            out["config_error"] = exc.message
    return out


def project_dict(p: Project, session: Session | None = None) -> dict:
    out = {"id": p.id, "name": p.name, "description": p.description, "crop": p.crop, "is_sample": p.is_sample, "archived": p.archived,
           "created_at": p.created_at.isoformat() + "Z", "updated_at": p.updated_at.isoformat() + "Z"}
    if session is not None:
        out["scenario_count"] = len(session.scalars(select(Scenario.id).where(Scenario.project_id == p.id, Scenario.archived.is_(False))).all())
    return out


def validate_scenario(session: Session, s: Scenario) -> None:
    """Build the typed config and check dataset coverage; store the outcome on the row."""
    messages = []
    cfg = build_config(s)
    if s.dataset_id:
        d = datasets.get_dataset(session, s.dataset_id)
        seasons, skipped, split = datasets.seasons_for(d, s.planting_mmdd, cfg.crop.season_length)
        if not seasons:
            messages.append("Dataset contains no complete season for this planting date and crop length")
        elif not split.train:
            messages.append(f"Only {len(seasons)} complete season(s): {split.rule}")
    else:
        messages.append("No weather dataset attached; simulations need one")
    s.validation_status = "valid" if not any("no complete season" in m or "No weather" in m for m in messages) else "incomplete"
    s.validation_messages = json.dumps(messages)


def get_project(session: Session, project_id: str) -> Project:
    p = session.get(Project, project_id)
    if not p:
        raise not_found("Project")
    return p


def get_scenario(session: Session, scenario_id: str) -> Scenario:
    s = session.get(Scenario, scenario_id)
    if not s:
        raise not_found("Scenario")
    return s


def ensure_sample_project(session: Session) -> tuple[Project, Scenario]:
    dataset = datasets.ensure_sample(session)
    project = session.scalar(select(Project).where(Project.is_sample.is_(True), Project.archived.is_(False)))
    if not project:
        project = Project(id=new_id(), name="Sample field (synthetic)", crop="maize", is_sample=True,
                          description="Synthetic demonstration field: maize on sandy loam near Tiruchirappalli, Tamil Nadu (10.79 N, 78.70 E). "
                                      "Weather is generated, not measured.")
        session.add(project)
        session.flush()
    scenario = session.scalar(select(Scenario).where(Scenario.project_id == project.id, Scenario.archived.is_(False)))
    if not scenario:
        scenario = Scenario(id=new_id(), project_id=project.id, name="Kharif maize — 350 mm, 10 readings", dataset_id=dataset.id)
        session.add(scenario)
        session.flush()
        validate_scenario(session, scenario)
    return project, scenario
