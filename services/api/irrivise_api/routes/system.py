"""Health, configuration defaults, diagnostics and sample-data reset."""
from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from irrivise_core.baselines.policies import METHODS
from irrivise_core.config import ACTIONS_MM, list_profiles, load_carat, load_crop, load_soil, load_training
from irrivise_core.config.schemas import RewardWeights, RiskConfig, SensorConfig, UncertaintyConfig
from irrivise_core.crops import aquacrop_adapter
from irrivise_core.envs.features import FEATURE_SPEC_VERSION, FEATURES
from irrivise_core.util.repro import package_versions

from ..config import get_settings
from ..db.models import ModelRecord, SimulationRun, WeatherDataset
from ..db.session import get_session
from ..services import artifacts, datasets, jobs
from ..services.scenarios import ensure_sample_project, project_dict, scenario_dict

router = APIRouter(tags=["system"])


def health_payload(session: Session) -> dict:
    session.execute(text("SELECT 1"))
    revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return {
        "api": "ok", "database": "ok", "schema_revision": revision, "worker": jobs.worker_status(session),
        "datasets": session.scalar(select(func.count()).select_from(WeatherDataset).where(WeatherDataset.archived.is_(False))),
        "sample_dataset": session.scalar(select(func.count()).select_from(WeatherDataset).where(WeatherDataset.source == "sample")) > 0,
        "models": session.scalar(select(func.count()).select_from(ModelRecord).where(ModelRecord.status == "ready")),
        "runs": session.scalar(select(func.count()).select_from(SimulationRun)),
        "active_jobs": session.scalar(text("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')")),
        "aquacrop": dict(zip(("available", "detail"), aquacrop_adapter.available())),
        "mode": "local single-user (no authentication); bind to localhost only",
    }


@router.get("/health")
def health(session: Session = Depends(get_session)):
    return health_payload(session)


@router.get("/config/defaults")
def defaults():
    crops = {name: load_crop(name).model_dump(mode="json") for name in list_profiles("crops")}
    soils = {name: load_soil(name).model_dump(mode="json") for name in list_profiles("soils")}
    presets = {name: load_training(name).model_dump(mode="json") for name in list_profiles("training")}
    return {"actions_mm": list(ACTIONS_MM), "crops": crops, "soils": soils, "training_presets": presets,
            "carat": load_carat("default").model_dump(mode="json"), "risk": RiskConfig().model_dump(), "reward": RewardWeights().model_dump(),
            "uncertainty": UncertaintyConfig().model_dump(), "sensor": SensorConfig().model_dump(), "sensor_modes": ["nominal", "missing", "biased", "stuck", "delayed"],
            "methods": [m.as_dict() for m in METHODS.values()], "feature_spec_version": FEATURE_SPEC_VERSION,
            "policy_features": [{"name": n, "description": d} for n, d in FEATURES],
            "units": {"irrigation": "mm/day", "seasonal_water": "mm", "soil_water_storage": "mm (root zone)", "theta": "m³/m³",
                      "eto": "mm/day", "yield": "t/ha", "water_productivity": "kg/m³", "root_depth": "m"}}


@router.get("/system/diagnostics")
def diagnostics(session: Session = Depends(get_session)):
    settings = get_settings()
    usage = shutil.disk_usage(settings.data_root)
    try:
        import psutil  # optional
        memory = {"total_bytes": psutil.virtual_memory().total, "available_bytes": psutil.virtual_memory().available}
    except ImportError:
        pages, size = os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else 0, os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 0
        memory = {"total_bytes": pages * size, "available_bytes": None}
    return {
        "health": health_payload(session), "cpu_count": os.cpu_count(), "memory": memory,
        "disk": {"free_bytes": usage.free, "artifacts_bytes": artifacts.disk_usage_bytes(), "quota_bytes": settings.storage_quota_bytes},
        "paths": {"data_root": settings.data_root.name, "database": "data/irrivise.sqlite3", "artifacts": "artifacts/"},
        "limits": {"max_upload_bytes": settings.max_upload_bytes, "max_queued_jobs": settings.max_queued_jobs,
                   "max_parallel_training": settings.max_parallel_training, "max_parallel_jobs": settings.max_parallel_other},
        "packages": package_versions(),
    }


@router.post("/system/reset-sample")
def reset_sample(session: Session = Depends(get_session)):
    """Re-register the synthetic fixture and the sample project (never deletes user data or results)."""
    datasets._load.cache_clear()
    dataset = datasets.ensure_sample(session)
    project, scenario = ensure_sample_project(session)
    return {"dataset": datasets.dataset_dict(dataset), "project": project_dict(project, session), "scenario": scenario_dict(scenario)}
