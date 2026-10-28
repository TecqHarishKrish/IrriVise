"""Durable job queue on SQLite: enqueue, atomic claim, strict transitions, progress events."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from irrivise_core.util.repro import sha256_json

from ..config import get_settings
from ..db.models import Job, JobEvent, WorkerHeartbeat, new_id, utcnow
from ..errors import ApiError, not_found

ACTIVE = ("queued", "running")
TERMINAL = ("succeeded", "failed", "cancelled", "interrupted")
TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"succeeded", "failed", "cancelled", "interrupted"},
}
KINDS = ("weather_fetch", "simulation", "training", "experiment")
HEAVY = ("training",)


def job_dict(job: Job) -> dict:
    return {"id": job.id, "kind": job.kind, "status": job.status, "phase": job.phase, "progress": round(job.progress, 2),
            "current_step": job.current_step, "total_steps": job.total_steps, "cancel_requested": job.cancel_requested,
            "payload": json.loads(job.payload_json or "{}"), "result": json.loads(job.result_json or "{}"), "error": job.error,
            "project_id": job.project_id, "scenario_id": job.scenario_id, "last_sequence": job.last_sequence,
            "created_at": _iso(job.created_at), "started_at": _iso(job.started_at), "finished_at": _iso(job.finished_at),
            "heartbeat_at": _iso(job.heartbeat_at), "status_url": f"/api/v1/jobs/{job.id}", "events_url": f"/api/v1/jobs/{job.id}/events"}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def enqueue(session: Session, kind: str, payload: dict, project_id: str | None, scenario_id: str | None,
            idempotency_key: str | None = None, total_steps: int = 0) -> tuple[Job, bool]:
    """Returns (job, created). Duplicate active submissions return the existing job."""
    if kind not in KINDS:
        raise ValueError("Unknown job kind")
    if idempotency_key:
        existing = session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing:
            return existing, False
    dedupe = sha256_json({"kind": kind, "payload": payload})
    duplicate = session.scalar(select(Job).where(Job.dedupe_key == dedupe, Job.status.in_(ACTIVE)))
    if duplicate:
        raise ApiError(409, "duplicate_job", "An identical job is already queued or running", {"job_id": duplicate.id})
    active = session.scalar(select(func.count()).select_from(Job).where(Job.status.in_(ACTIVE)))
    if active >= get_settings().max_queued_jobs:
        raise ApiError(429, "queue_full", f"Too many active jobs ({active}); wait for some to finish or cancel them")
    job = Job(id=new_id(), kind=kind, payload_json=json.dumps(payload, default=str), project_id=project_id, scenario_id=scenario_id,
              dedupe_key=dedupe, idempotency_key=idempotency_key, total_steps=total_steps)
    session.add(job)
    session.flush()
    add_event(session, job, "queued", "Job queued")
    return job, True


def add_event(session: Session, job: Job, phase: str, message: str = "", metric_name: str | None = None,
              metric_value: float | None = None, data: dict | None = None) -> JobEvent:
    job.last_sequence += 1
    event = JobEvent(job_id=job.id, sequence=job.last_sequence, status=job.status, phase=phase[:120], current_step=job.current_step,
                     total_steps=job.total_steps, metric_name=metric_name, metric_value=metric_value, message=message[:500],
                     data_json=json.dumps(data, default=str)[:20000] if data else None)
    session.add(event)
    session.flush()
    _trim_events(session, job.id)
    return event


def _trim_events(session: Session, job_id: str, keep: int = 2000) -> None:
    count = session.scalar(select(func.count()).select_from(JobEvent).where(JobEvent.job_id == job_id))
    if count and count > keep:
        cutoff = session.scalar(select(JobEvent.sequence).where(JobEvent.job_id == job_id).order_by(JobEvent.sequence.desc()).offset(keep).limit(1))
        session.execute(text("DELETE FROM job_events WHERE job_id=:j AND sequence<=:c AND metric_name IS NULL"), {"j": job_id, "c": cutoff})


def transition(session: Session, job: Job, status: str, phase: str | None = None, error: str | None = None, message: str = "") -> None:
    if status not in TRANSITIONS.get(job.status, set()):
        raise ValueError(f"Illegal job transition {job.status} → {status}")
    job.status = status
    if phase:
        job.phase = phase
    if status == "running":
        job.started_at = utcnow()
        job.heartbeat_at = utcnow()
    if status in TERMINAL:
        job.finished_at = utcnow()
        if status == "succeeded":
            job.progress = 100.0
    if error:
        job.error = error[:2000]
    add_event(session, job, phase or status, message or status)


def get_job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise not_found("Job")
    return job


def request_cancel(session: Session, job: Job) -> Job:
    if job.status == "queued":
        job.cancel_requested = True
        transition(session, job, "cancelled", "cancelled", message="Cancelled before start")
    elif job.status == "running":
        job.cancel_requested = True
        add_event(session, job, job.phase, "Cancellation requested; the worker stops at the next safe checkpoint")
    else:
        raise ApiError(409, "not_cancellable", f"Job is already {job.status}")
    return job


def claim_next(session: Session, worker_id: str, kinds: tuple[str, ...]) -> Job | None:
    """Atomic claim: a conditional UPDATE guarantees only one worker wins a queued job."""
    if not kinds:
        return None
    candidate = session.scalar(select(Job.id).where(Job.status == "queued", Job.kind.in_(kinds)).order_by(Job.created_at).limit(1))
    if not candidate:
        return None
    now = utcnow()
    result = session.execute(update(Job).where(Job.id == candidate, Job.status == "queued")
                             .values(status="running", worker_id=worker_id, started_at=now, heartbeat_at=now, phase="starting"))
    if result.rowcount != 1:
        return None
    job = session.get(Job, candidate)
    session.refresh(job)
    add_event(session, job, "starting", f"Claimed by worker {worker_id}")
    return job


def recover_stale(session: Session, timeout_s: int, only_worker: str | None = None) -> list[str]:
    """Mark running jobs whose heartbeat stopped (worker died) as interrupted. Never resumed silently."""
    limit = utcnow() - timedelta(seconds=timeout_s)
    query = select(Job).where(Job.status == "running")
    stale = []
    for job in session.scalars(query).all():
        if (only_worker and job.worker_id == only_worker) or (job.heartbeat_at is None or job.heartbeat_at < limit):
            transition(session, job, "interrupted", "interrupted", error="Worker stopped before completion; partial artifacts are not used. Re-queue to run again.")
            stale.append(job.id)
    return stale


def worker_status(session: Session) -> dict:
    beat = session.scalar(select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen.desc()).limit(1))
    if not beat:
        return {"status": "not_started", "message": "No worker has connected. Start it with: python -m irrivise_api.worker"}
    age = (utcnow() - beat.last_seen).total_seconds()
    return {"status": "online" if age < 15 else "offline", "worker_id": beat.worker_id, "last_seen_seconds_ago": round(age, 1),
            "running_jobs": beat.running_jobs}
