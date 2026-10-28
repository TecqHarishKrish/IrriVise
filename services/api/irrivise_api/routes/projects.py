"""Projects and field scenarios."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Project, Scenario, new_id
from ..db.session import get_session
from ..errors import ApiError
from ..schemas import ProjectIn, ProjectPatch, ScenarioIn, ScenarioPatch
from ..services import datasets
from ..services.scenarios import (build_config, ensure_sample_project, get_project, get_scenario, project_dict, scenario_dict,
                                  validate_advanced, validate_scenario)

router = APIRouter(tags=["projects"])


@router.get("/projects")
def list_projects(include_archived: bool = False, session: Session = Depends(get_session)):
    query = select(Project).order_by(Project.created_at.desc())
    if not include_archived:
        query = query.where(Project.archived.is_(False))
    return [project_dict(p, session) for p in session.scalars(query).all()]


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, session: Session = Depends(get_session)):
    project = Project(id=new_id(), **body.model_dump())
    session.add(project)
    session.flush()
    return project_dict(project, session)


@router.post("/projects/sample", status_code=201)
def sample_project(session: Session = Depends(get_session)):
    project, scenario = ensure_sample_project(session)
    return {"project": project_dict(project, session), "scenario": scenario_dict(scenario)}


@router.get("/projects/{project_id}")
def read_project(project_id: str, session: Session = Depends(get_session)):
    return project_dict(get_project(session, project_id), session)


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectPatch, session: Session = Depends(get_session)):
    project = get_project(session, project_id)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(project, key, value)
    session.flush()
    return project_dict(project, session)


@router.delete("/projects/{project_id}")
def archive_project(project_id: str, session: Session = Depends(get_session)):
    """Archive (soft delete); runs and artifacts are preserved for reproducibility."""
    project = get_project(session, project_id)
    project.archived = True
    return project_dict(project, session)


@router.get("/projects/{project_id}/scenarios")
def list_scenarios(project_id: str, include_archived: bool = False, session: Session = Depends(get_session)):
    get_project(session, project_id)
    query = select(Scenario).where(Scenario.project_id == project_id).order_by(Scenario.created_at.desc())
    if not include_archived:
        query = query.where(Scenario.archived.is_(False))
    return [scenario_dict(s) for s in session.scalars(query).all()]


@router.post("/projects/{project_id}/scenarios", status_code=201)
def create_scenario(project_id: str, body: ScenarioIn, session: Session = Depends(get_session)):
    project = get_project(session, project_id)
    if project.archived:
        raise ApiError(409, "project_archived", "Cannot add scenarios to an archived project")
    data = body.model_dump()
    advanced = validate_advanced(data.pop("advanced"))
    if data["dataset_id"]:
        datasets.get_dataset(session, data["dataset_id"])
    scenario = Scenario(id=new_id(), project_id=project_id, config_json=json.dumps(advanced), **data)
    build_config(scenario)  # raises 422 with details if invalid
    session.add(scenario)
    session.flush()
    validate_scenario(session, scenario)
    return scenario_dict(scenario)


@router.get("/scenarios/{scenario_id}")
def read_scenario(scenario_id: str, session: Session = Depends(get_session)):
    return scenario_dict(get_scenario(session, scenario_id))


@router.patch("/scenarios/{scenario_id}")
def update_scenario(scenario_id: str, body: ScenarioPatch, session: Session = Depends(get_session)):
    scenario = get_scenario(session, scenario_id)
    data = body.model_dump(exclude_unset=True)
    if "advanced" in data:
        scenario.config_json = json.dumps(validate_advanced(data.pop("advanced") or {}))
    if data.get("dataset_id"):
        datasets.get_dataset(session, data["dataset_id"])
    for key, value in data.items():
        setattr(scenario, key, value)
    build_config(scenario)
    validate_scenario(session, scenario)
    session.flush()
    return scenario_dict(scenario)


@router.get("/scenarios/{scenario_id}/seasons")
def scenario_seasons(scenario_id: str, session: Session = Depends(get_session)):
    scenario = get_scenario(session, scenario_id)
    if not scenario.dataset_id:
        return {"seasons": [], "split": None, "skipped": [], "message": "No dataset attached"}
    cfg = build_config(scenario)
    d = datasets.get_dataset(session, scenario.dataset_id)
    seasons, skipped, split = datasets.seasons_for(d, scenario.planting_mmdd, cfg.crop.season_length)
    return {"seasons": [{"season_id": s.season_id, "start": s.start, "end": s.dates[-1], "rain_mm": round(float(s.rain_mm.sum()), 2),
                         "split": "train" if s.season_id in split.train else "validation" if s.season_id in split.validation else "test"} for s in seasons],
            "split": split.as_dict(), "skipped": skipped, "season_length_days": cfg.crop.season_length}
