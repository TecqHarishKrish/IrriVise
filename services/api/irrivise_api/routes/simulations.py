"""Simulation runs: enqueue, list, summaries, daily traces, CARAT decisions, evaluation-only truth."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from irrivise_core.baselines.policies import METHODS

from ..db.models import ModelRecord, SimulationRun
from ..db.session import get_session
from ..errors import ApiError, not_found
from ..schemas import SimulationIn
from ..services import artifacts, jobs
from ..services.scenarios import build_config, get_scenario

router = APIRouter(tags=["simulations"])
NUMERIC_SKIP = {"date", "constraint_status", "risk_flags", "measurement_status", "method", "method_code", "method_label", "yield_label", "season_id", "aquacrop_error"}


def run_dict(r: SimulationRun) -> dict:
    method = METHODS.get(r.method)
    return {"id": r.id, "job_id": r.job_id, "scenario_id": r.scenario_id, "dataset_id": r.dataset_id, "season_id": r.season_id, "split": r.split,
            "method": r.method, "method_code": method.code if method else r.method, "method_label": method.label if method else r.method,
            "model_id": r.model_id, "seed": r.seed, "status": r.status, "config_sha256": r.config_sha256,
            "summary": json.loads(r.summary_json), "created_at": r.created_at.isoformat() + "Z"}


def get_run(session: Session, run_id: str) -> SimulationRun:
    r = session.get(SimulationRun, run_id)
    if not r:
        raise not_found("Run")
    return r


def _coerce(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if key in NUMERIC_SKIP:
            out[key] = value
        elif value in ("", None):
            out[key] = None
        elif value in ("True", "False"):
            out[key] = value == "True"
        else:
            try:
                out[key] = float(value)
            except ValueError:
                out[key] = value
    return out


@router.post("/simulations", status_code=202)
def enqueue(body: SimulationIn, idempotency_key: str | None = Header(default=None, max_length=100), session: Session = Depends(get_session)):
    scenario = get_scenario(session, body.scenario_id)
    build_config(scenario)
    if not scenario.dataset_id:
        raise ApiError(422, "scenario_incomplete", "Attach a weather dataset to the scenario before simulating")
    spec = METHODS[body.method]
    if spec.needs_model:
        if not body.model_id:
            raise ApiError(422, "model_required", f"{spec.label} needs a trained PPO model. Train one in the Model Training Lab or pick a non-PPO method.")
        model = session.get(ModelRecord, body.model_id)
        if not model or model.status != "ready":
            raise ApiError(404, "not_found", "Model not found")
    job, _ = jobs.enqueue(session, "simulation", body.model_dump(), scenario.project_id, scenario.id, idempotency_key, total_steps=4)
    return jobs.job_dict(job)


@router.get("/simulations")
def list_runs(scenario_id: str | None = None, method: str | None = None, limit: int = Query(100, ge=1, le=500),
              session: Session = Depends(get_session)):
    query = select(SimulationRun).order_by(SimulationRun.created_at.desc()).limit(limit)
    if scenario_id:
        query = query.where(SimulationRun.scenario_id == scenario_id)
    if method:
        query = query.where(SimulationRun.method == method)
    return [run_dict(r) for r in session.scalars(query).all()]


@router.get("/simulations/{run_id}")
def read_run(run_id: str, session: Session = Depends(get_session)):
    r = get_run(session, run_id)
    out = run_dict(r)
    manifest = artifacts.run_dir(r.id) / "manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text())
        data.pop("hidden_parameters_evaluation_only", None)  # decision views never receive hidden truth
        out["manifest"] = data
    return out


@router.get("/simulations/{run_id}/daily")
def daily(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(400, ge=1, le=2000), session: Session = Depends(get_session)):
    """Operational daily trace. Contains no hidden reference state."""
    r = get_run(session, run_id)
    rows = [_coerce(x) for x in artifacts.read_csv(artifacts.run_dir(r.id) / "daily.csv")]
    return {"run_id": r.id, "total": len(rows), "offset": offset, "limit": limit, "rows": rows[offset:offset + limit],
            "provenance": "estimated twin and applied actions; no hidden reference values"}


@router.get("/simulations/{run_id}/decisions")
def decisions(run_id: str, day: int | None = Query(None, ge=1, le=400), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=400),
              session: Session = Depends(get_session)):
    r = get_run(session, run_id)
    traces = json.loads((artifacts.run_dir(r.id) / "decisions.json").read_text())
    if day is not None:
        match = [t for t in traces if t["day"] == day]
        if not match:
            raise not_found("Decision day")
        return {"run_id": r.id, "total": len(traces), "rows": match}
    return {"run_id": r.id, "total": len(traces), "offset": offset, "limit": limit, "rows": traces[offset:offset + limit]}


@router.get("/simulations/{run_id}/evaluation")
def evaluation(run_id: str, session: Session = Depends(get_session)):
    """POST-RUN EVALUATION ONLY: hidden simulated reference vs twin estimate. Never used for decisions."""
    r = get_run(session, run_id)
    directory = artifacts.run_dir(r.id)
    rows = [_coerce(x) for x in artifacts.read_csv(directory / "evaluation_truth.csv")]
    manifest = json.loads((directory / "manifest.json").read_text())
    return {"run_id": r.id, "label": "SIMULATED REFERENCE — evaluation only; not available to the policy, CARAT or risk manager",
            "hidden_parameters": manifest.get("hidden_parameters_evaluation_only"), "rows": rows}
