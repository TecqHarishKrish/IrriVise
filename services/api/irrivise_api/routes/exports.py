"""Validated exports: ZIP bundles, CSV, JSON and printable HTML reports."""
from __future__ import annotations

import io
import json
import zipfile

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from irrivise_core.util.repro import sha256_file

from ..db.models import ExperimentGroup, ExportRecord, ModelRecord, new_id
from ..db.session import get_session
from ..errors import ApiError, not_found
from ..schemas import ExportIn
from ..services import artifacts, report
from .experiments import experiment_dict
from .simulations import _coerce, get_run, run_dict
from .training import model_dict

router = APIRouter(tags=["exports"])
MEDIA = {"zip": "application/zip", "csv": "text/csv", "json": "application/json", "html": "text/html"}


def export_dict(e: ExportRecord) -> dict:
    return {"id": e.id, "source_type": e.source_type, "source_id": e.source_id, "format": e.format, "sha256": e.sha256, "bytes": e.bytes,
            "created_at": e.created_at.isoformat() + "Z", "download_url": f"/api/v1/exports/{e.id}"}


def _verify(directory, manifest: dict) -> None:
    """Exports must reconcile with saved artifacts: verify recorded file hashes first."""
    for name, digest in (manifest.get("files") or {}).items():
        if sha256_file(directory / name) != digest:
            raise ApiError(409, "artifact_modified", f"{name} no longer matches its recorded SHA-256; refusing to export")


def _build(session: Session, body: ExportIn) -> tuple[bytes, str]:
    if body.source_type == "run":
        run = run_dict(get_run(session, body.source_id))
        directory = artifacts.run_dir(body.source_id)
        manifest = json.loads((directory / "manifest.json").read_text())
        _verify(directory, manifest)
        daily = [_coerce(r) for r in artifacts.read_csv(directory / "daily.csv")]
        if body.format == "csv":
            return (directory / "daily.csv").read_bytes(), "daily.csv"
        if body.format == "json":
            return json.dumps({"run": run, "manifest": manifest}, indent=1, default=str).encode(), "run.json"
        if body.format == "html":
            return report.run_report(run, daily, manifest).encode(), "report.html"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            for name in ("daily.csv", "decisions.json", "evaluation_truth.csv", "summary.json", "manifest.json"):
                z.write(directory / name, name)
            z.writestr("report.html", report.run_report(run, daily, manifest))
            z.writestr("README.txt", "IrriVise run export. evaluation_truth.csv is the hidden SIMULATED reference (evaluation only).\n"
                                     "Yields are proxies (surrogate) or AquaCrop-simulated; none are field measurements.\n")
        return buffer.getvalue(), "run.zip"
    if body.source_type == "experiment":
        group = session.get(ExperimentGroup, body.source_id)
        if not group:
            raise not_found("Experiment")
        if not group.summary_json:
            raise ApiError(409, "not_ready", "Experiment has no results yet")
        exp = experiment_dict(group, session, full=True)
        directory = artifacts.experiment_dir(group.id)
        manifest = exp.get("manifest") or {}
        _verify(directory, manifest)
        if body.format == "csv":
            return (directory / "results.csv").read_bytes(), "results.csv"
        if body.format == "json":
            return json.dumps(exp, indent=1, default=str).encode(), "experiment.json"
        if body.format == "html":
            return report.experiment_report(exp, manifest).encode(), "report.html"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            for name in ("results.csv", "summary.json", "manifest.json"):
                z.write(directory / name, name)
            z.writestr("report.html", report.experiment_report(exp, manifest))
        return buffer.getvalue(), "experiment.zip"
    m = session.get(ModelRecord, body.source_id)
    if not m:
        raise not_found("Model")
    model = model_dict(m, with_manifest=True)
    if body.format in {"json", "zip", "csv"}:
        if body.format == "csv":
            raise ApiError(422, "unsupported_format", "Models export as json, zip (manifest + report) or html")
        if body.format == "json":
            return json.dumps(model, indent=1, default=str).encode(), "model.json"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(model["manifest"], indent=1, default=str))
            z.writestr("report.html", report.model_report(model))
            z.writestr("README.txt", "Checkpoint binaries are not bundled; they stay in artifacts/models with the SHA-256 above.\n")
        return buffer.getvalue(), "model.zip"
    return report.model_report(model).encode(), "report.html"


@router.post("/exports", status_code=201)
def create_export(body: ExportIn, session: Session = Depends(get_session)):
    content, _ = _build(session, body)
    export_id = new_id()
    path = artifacts.export_dir() / f"{export_id}.{body.format}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    record = ExportRecord(id=export_id, source_type=body.source_type, source_id=body.source_id, format=body.format,
                          path=artifacts.relative(path), sha256=sha256_file(path), bytes=len(content))
    session.add(record)
    session.flush()
    return export_dict(record)


@router.get("/exports")
def list_exports(session: Session = Depends(get_session)):
    return [export_dict(e) for e in session.scalars(select(ExportRecord).order_by(ExportRecord.created_at.desc()).limit(200)).all()]


@router.get("/exports/{export_id}")
def download(export_id: str, session: Session = Depends(get_session)):
    record = session.get(ExportRecord, artifacts.check_id(export_id))
    if not record:
        raise not_found("Export")
    path = artifacts.safe_join(*record.path.split("/"))
    if not path.is_file() or sha256_file(path) != record.sha256:
        raise ApiError(410, "export_unavailable", "Export file is missing or was modified; create a new export")
    filename = f"irrivise-{record.source_type}-{record.source_id[:8]}.{record.format}"
    disposition = "inline" if record.format == "html" else "attachment"
    return FileResponse(path, media_type=MEDIA[record.format], filename=filename, content_disposition_type=disposition)
