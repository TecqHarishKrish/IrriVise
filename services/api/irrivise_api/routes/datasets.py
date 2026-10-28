"""Weather datasets: list, preview, CSV import, NASA POWER fetch jobs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from irrivise_core.data.nasa_power import build_query

from ..config import get_settings
from ..db.models import WeatherDataset
from ..db.session import get_session
from ..errors import ApiError
from ..schemas import NasaPowerIn
from ..services import datasets, jobs
from ..services.artifacts import safe_join

router = APIRouter(tags=["datasets"])


@router.get("/datasets")
def list_datasets(session: Session = Depends(get_session)):
    datasets.ensure_sample(session)
    rows = session.scalars(select(WeatherDataset).where(WeatherDataset.archived.is_(False)).order_by(WeatherDataset.created_at)).all()
    return [datasets.dataset_dict(d) for d in rows]


@router.get("/datasets/{dataset_id}")
def read_dataset(dataset_id: str, session: Session = Depends(get_session)):
    return datasets.dataset_dict(datasets.get_dataset(session, dataset_id))


@router.get("/datasets/{dataset_id}/preview")
def preview(dataset_id: str, planting_mmdd: str = "06-15", season_length_days: int = 140, max_points: int = 400,
            session: Session = Depends(get_session)):
    if not 1 <= season_length_days <= 250 or not 10 <= max_points <= 5000:
        raise ApiError(422, "validation_error", "season_length_days must be 1–250 and max_points 10–5000")
    try:
        return datasets.preview(datasets.get_dataset(session, dataset_id), planting_mmdd, season_length_days, max_points)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc


@router.get("/datasets/{dataset_id}/download")
def download(dataset_id: str, session: Session = Depends(get_session)):
    d = datasets.get_dataset(session, dataset_id)
    return FileResponse(safe_join(*d.file_path.split("/")), media_type="text/csv", filename=f"irrivise-weather-{d.id[:8]}.csv")


@router.delete("/datasets/{dataset_id}")
def archive(dataset_id: str, session: Session = Depends(get_session)):
    d = datasets.get_dataset(session, dataset_id)
    if d.source == "sample":
        raise ApiError(409, "sample_protected", "The synthetic sample dataset cannot be archived")
    d.archived = True
    return datasets.dataset_dict(d)


@router.post("/datasets/import", status_code=201)
async def import_csv(file: UploadFile = File(...), name: str = Form(..., min_length=2, max_length=120),
                     latitude: float | None = Form(None, ge=-90, le=90), longitude: float | None = Form(None, ge=-180, le=180),
                     session: Session = Depends(get_session)):
    limit = get_settings().max_upload_bytes
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise ApiError(415, "unsupported_file", "Only .csv files are accepted")
    if file.content_type not in {"text/csv", "application/vnd.ms-excel", "application/octet-stream", "text/plain"}:
        raise ApiError(415, "unsupported_file", f"Unsupported content type {file.content_type}")
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise ApiError(413, "payload_too_large", f"File exceeds {limit // 1_000_000} MB limit")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError(422, "invalid_weather_csv", "File is not UTF-8 text") from exc
    if "<" in name or ">" in name:
        raise ApiError(422, "validation_error", "Angle brackets are not allowed in names")
    record = datasets.import_csv(session, name.strip(), text, latitude, longitude)
    return datasets.dataset_dict(record)


@router.post("/datasets/nasa-power", status_code=202)
def nasa_power(body: NasaPowerIn, idempotency_key: str | None = Header(default=None, max_length=100), session: Session = Depends(get_session)):
    try:
        build_query(body.latitude, body.longitude, body.start, body.end, body.time_standard)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    job, _ = jobs.enqueue(session, "weather_fetch", body.model_dump(mode="json"), None, None, idempotency_key)
    return jobs.job_dict(job)
