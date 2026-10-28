"""Job status, cancellation and live progress (SSE with polling fallback)."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Job, JobEvent
from ..db.session import get_session, session_scope
from ..errors import ApiError
from ..services import jobs

router = APIRouter(tags=["jobs"])


def event_dict(e: JobEvent) -> dict:
    return {"sequence": e.sequence, "job_id": e.job_id, "status": e.status, "phase": e.phase, "current_step": e.current_step,
            "total_steps": e.total_steps, "metric_name": e.metric_name, "metric_value": e.metric_value,
            "timestamp": e.timestamp.isoformat() + "Z", "message": e.message, "data": json.loads(e.data_json) if e.data_json else None}


@router.get("/jobs")
def list_jobs(status: str | None = None, kind: str | None = None, scenario_id: str | None = None, limit: int = Query(50, ge=1, le=200),
              offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
    query = select(Job).order_by(Job.created_at.desc()).offset(offset).limit(limit)
    if status:
        query = query.where(Job.status.in_(status.split(",")))
    if kind:
        query = query.where(Job.kind == kind)
    if scenario_id:
        query = query.where(Job.scenario_id == scenario_id)
    return [jobs.job_dict(j) for j in session.scalars(query).all()]


@router.get("/jobs/{job_id}")
def read_job(job_id: str, session: Session = Depends(get_session)):
    job = jobs.get_job(session, job_id)
    out = jobs.job_dict(job)
    recent = session.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.sequence.desc()).limit(20)).all()
    out["log_excerpt"] = [event_dict(e) for e in reversed(recent)]
    return out


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str, session: Session = Depends(get_session)):
    return jobs.job_dict(jobs.request_cancel(session, jobs.get_job(session, job_id)))


def _events_after(job_id: str, after: int, limit: int = 500) -> tuple[list[dict], str]:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if not job:
            raise ApiError(404, "not_found", "Job not found")
        rows = s.scalars(select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.sequence > after)
                         .order_by(JobEvent.sequence).limit(limit)).all()
        return [event_dict(e) for e in rows], job.status


@router.get("/jobs/{job_id}/events")
async def events(job_id: str, request: Request, after: int = Query(0, ge=0), format: str = Query("sse", pattern="^(sse|json)$"),
                 last_event_id: str | None = Header(default=None)):
    """SSE stream of progress events (``id`` = sequence; resumable via Last-Event-ID).

    Polling fallback: ``?format=json&after=<sequence>`` returns the same events as JSON.
    """
    start = after
    if last_event_id and last_event_id.isdigit():
        start = max(start, int(last_event_id))
    if format == "json":
        rows, status = _events_after(job_id, start)
        return {"job_id": job_id, "status": status, "events": rows, "terminal": status in jobs.TERMINAL}
    _events_after(job_id, 0, limit=1)  # 404 before opening the stream

    async def stream():
        cursor, idle = start, 0.0
        yield "retry: 3000\n\n"
        while True:
            if await request.is_disconnected():
                return
            rows, status = await asyncio.to_thread(_events_after, job_id, cursor)
            for row in rows:
                cursor = row["sequence"]
                yield f"id: {cursor}\nevent: progress\ndata: {json.dumps(row)}\n\n"
            if status in jobs.TERMINAL and not rows:
                yield f"event: end\ndata: {json.dumps({'status': status})}\n\n"
                return
            if rows:
                idle = 0.0
            else:
                idle += 0.75
                if idle >= 15:
                    idle = 0.0
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.75)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
