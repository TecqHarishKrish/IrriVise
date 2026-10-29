import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Fresh data root + database per test; lifespan runs Alembic migrations on a clean DB."""
    monkeypatch.setenv("IRRIVISE_DATA_ROOT", str(tmp_path))
    from fastapi.testclient import TestClient

    from irrivise_api import config
    from irrivise_api.db import session
    from irrivise_api.services import datasets

    config.reset_settings_cache()
    session.dispose_all()
    datasets._load.cache_clear()
    from irrivise_api.main import create_app

    with TestClient(create_app()) as c:
        yield c
    session.dispose_all()
    config.reset_settings_cache()


@pytest.fixture()
def sample(client):
    return client.post("/api/v1/projects/sample").json()


def run_next_job():
    """Claim and execute one queued job in-process, exactly as the worker child does."""
    from irrivise_api.db.session import session_scope
    from irrivise_api.services import jobs
    from irrivise_api.worker.tasks import execute

    with session_scope() as s:
        job = jobs.claim_next(s, "test-worker", jobs.KINDS)
        job_id = job.id if job else None
    if job_id:
        execute(job_id)
    return job_id
