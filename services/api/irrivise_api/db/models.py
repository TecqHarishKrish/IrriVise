"""SQLAlchemy 2 ORM models (metadata only; large daily traces live in artifact files)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    crop: Mapped[str] = mapped_column(String(40), default="maize")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class WeatherDataset(Base):
    __tablename__ = "weather_datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(20))  # sample | uploaded | nasa_power
    file_path: Mapped[str] = mapped_column(String(300))
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    rows: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_standard: Mapped[str] = mapped_column(String(40), default="n/a")
    units_json: Mapped[str] = mapped_column(Text, default="{}")
    validation_json: Mapped[str] = mapped_column(Text, default="{}")
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    license: Mapped[str] = mapped_column(Text, default="")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[float] = mapped_column(Float, default=10.79)
    longitude: Mapped[float] = mapped_column(Float, default=78.70)
    crop_profile: Mapped[str] = mapped_column(String(40), default="maize")
    soil_profile: Mapped[str] = mapped_column(String(40), default="sandy_loam")
    planting_mmdd: Mapped[str] = mapped_column(String(5), default="06-15")
    daily_max_mm: Mapped[float] = mapped_column(Float, default=20.0)
    seasonal_budget_mm: Mapped[float] = mapped_column(Float, default=350.0)
    observation_budget: Mapped[int] = mapped_column(Integer, default=10)
    sensor_noise_m3m3: Mapped[float] = mapped_column(Float, default=0.02)
    sensor_mode: Mapped[str] = mapped_column(String(20), default="nominal")
    initial_fraction_mean: Mapped[float] = mapped_column(Float, default=0.7)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("weather_datasets.id"), nullable=True)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    validation_status: Mapped[str] = mapped_column(String(20), default="valid")
    validation_messages: Mapped[str] = mapped_column(Text, default="[]")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(20))  # weather_fetch | simulation | training | experiment
    status: Mapped[str] = mapped_column(String(20), default="queued")
    phase: Mapped[str] = mapped_column(String(120), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scenario_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(default=utcnow)
    status: Mapped[str] = mapped_column(String(20))
    phase: Mapped[str] = mapped_column(String(120), default="")
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    metric_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(String(500), default="")
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    pid: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(default=utcnow)
    running_jobs: Mapped[int] = mapped_column(Integer, default=0)


class ModelRecord(Base):
    __tablename__ = "models"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    scenario_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    algorithm: Mapped[str] = mapped_column(String(20), default="PPO")
    preset: Mapped[str] = mapped_column(String(20))
    seed: Mapped[int] = mapped_column(Integer)
    actual_timesteps: Mapped[int] = mapped_column(Integer)
    checkpoint_path: Mapped[str] = mapped_column(String(300))
    checkpoint_sha256: Mapped[str] = mapped_column(String(64))
    manifest_path: Mapped[str] = mapped_column(String(300))
    config_sha256: Mapped[str] = mapped_column(String(64))
    validation_json: Mapped[str] = mapped_column(Text, default="{}")
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    research_quality: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, unique=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(String(36))
    season_id: Mapped[str] = mapped_column(String(20))
    split: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(40))
    model_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="succeeded")
    config_sha256: Mapped[str] = mapped_column(String(64))
    artifact_dir: Mapped[str] = mapped_column(String(300))
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    aquacrop_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ExperimentGroup(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, unique=True)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"), index=True)
    model_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    config_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    artifact_dir: Mapped[str | None] = mapped_column(String(300), nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ExportRecord(Base):
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[str] = mapped_column(String(36))
    format: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
