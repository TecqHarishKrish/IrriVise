"""IrriVise FastAPI application. Heavy work is enqueued for the separate worker process.

Run: ``uvicorn irrivise_api.main:app --host 127.0.0.1 --port 8000`` (local single-user mode).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import errors
from .config import get_settings
from .db.session import migrate, session_scope
from .routes import analytics, datasets, experiments, exports, jobs, projects, simulations, system, training
from .services.datasets import ensure_sample

API_PREFIX = "/api/v1"
log = logging.getLogger("irrivise.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    revision = migrate()
    with session_scope() as session:
        ensure_sample(session)
    log.info("IrriVise API ready (schema %s)", revision)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="IrriVise API", version="0.2.0", lifespan=lifespan,
                  description="Local research API for IrriVise — Think Before You Water (CARAT method). "
                              "All farm outcomes are simulated; see /api/v1/config/defaults for units.")
    app.add_middleware(CORSMiddleware, allow_origins=list(get_settings().cors_origins), allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "Idempotency-Key", "Last-Event-ID", "X-Request-ID"])
    errors.install(app)
    for module in (system, projects, datasets, simulations, training, experiments, jobs, exports, analytics):
        app.include_router(module.router, prefix=API_PREFIX)
    app.add_api_route("/health", system.health, methods=["GET"], tags=["system"])
    return app


app = create_app()
