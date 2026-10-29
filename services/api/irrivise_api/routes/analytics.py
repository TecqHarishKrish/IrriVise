"""Aggregated analytics over saved runs (re-derived from stored summaries)."""
from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from irrivise_core.baselines.policies import METHODS
from irrivise_core.evaluation.stats import describe

from ..db.models import SimulationRun
from ..db.session import get_session

router = APIRouter(tags=["analytics"])
METRICS = ("seasonal_irrigation_mm", "yield_proxy_t_ha", "irrigation_wp_proxy_kg_m3", "cumulative_stress", "stress_days",
           "observation_count", "twin_rmse_mm", "estimated_regret_mean", "gross_voi_mean", "runtime_seconds")


@router.get("/analytics/overview")
def overview(scenario_id: str | None = None, session: Session = Depends(get_session)):
    query = select(SimulationRun)
    if scenario_id:
        query = query.where(SimulationRun.scenario_id == scenario_id)
    runs = session.scalars(query).all()
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        s = json.loads(r.summary_json)
        aq = s.get("aquacrop") or {}
        s["aquacrop_yield_t_ha"] = aq.get("aquacrop_simulated_dry_yield_t_ha")
        groups[r.method].append(s)
    methods = []
    for key, items in groups.items():
        spec = METHODS.get(key)
        entry = {"method": key, "code": spec.code if spec else key, "label": spec.label if spec else key, "runs": len(items)}
        for metric in METRICS + ("aquacrop_yield_t_ha",):
            entry[metric] = describe([i.get(metric) for i in items])
        methods.append(entry)
    return {"scenario_id": scenario_id, "total_runs": len(runs), "methods": sorted(methods, key=lambda m: m["code"]),
            "note": "Single runs differ in season and seed; use Experiment Benchmark for matched, paired comparisons."}
