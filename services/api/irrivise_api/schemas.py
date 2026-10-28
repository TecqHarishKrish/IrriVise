"""Pydantic v2 request models for the REST API (responses are typed dicts documented in OpenAPI)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from irrivise_core.baselines.policies import METHODS


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _no_markup(value: str) -> str:
    if "<" in value or ">" in value:
        raise ValueError("Angle brackets are not allowed")
    return value


class ProjectIn(_In):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=1000)
    crop: Literal["maize"] = "maize"

    @field_validator("name", "description")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _no_markup(v)


class ProjectPatch(_In):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    archived: bool | None = None

    @field_validator("name", "description")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return v if v is None else _no_markup(v)


class ScenarioIn(_In):
    name: str = Field(min_length=2, max_length=100)
    latitude: float = Field(default=10.79, ge=-90, le=90)
    longitude: float = Field(default=78.70, ge=-180, le=180)
    crop_profile: str = Field(default="maize", pattern=r"^[a-z0-9_]{1,40}$")
    soil_profile: str = Field(default="sandy_loam", pattern=r"^[a-z0-9_]{1,40}$")
    planting_mmdd: str = Field(default="06-15", pattern=r"^\d{2}-\d{2}$")
    daily_max_mm: float = Field(default=20, ge=0, le=100)
    seasonal_budget_mm: float = Field(default=350, ge=0, le=3000)
    observation_budget: int = Field(default=10, ge=0, le=365)
    sensor_noise_m3m3: float = Field(default=0.02, ge=0, le=0.2)
    sensor_mode: Literal["nominal", "missing", "biased", "stuck", "delayed"] = "nominal"
    initial_fraction_mean: float = Field(default=0.7, ge=0, le=1)
    dataset_id: str | None = Field(default=None, max_length=36)
    advanced: dict = Field(default_factory=dict, description="Optional overrides: carat, risk, reward, uncertainty sections")

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _no_markup(v)


class ScenarioPatch(_In):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    soil_profile: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,40}$")
    planting_mmdd: str | None = Field(default=None, pattern=r"^\d{2}-\d{2}$")
    daily_max_mm: float | None = Field(default=None, ge=0, le=100)
    seasonal_budget_mm: float | None = Field(default=None, ge=0, le=3000)
    observation_budget: int | None = Field(default=None, ge=0, le=365)
    sensor_noise_m3m3: float | None = Field(default=None, ge=0, le=0.2)
    sensor_mode: Literal["nominal", "missing", "biased", "stuck", "delayed"] | None = None
    initial_fraction_mean: float | None = Field(default=None, ge=0, le=1)
    dataset_id: str | None = Field(default=None, max_length=36)
    advanced: dict | None = None
    archived: bool | None = None


class NasaPowerIn(_In):
    name: str = Field(default="NASA POWER daily", min_length=2, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    start: date
    end: date
    time_standard: Literal["UTC", "LST"] = "LST"


class SimulationIn(_In):
    scenario_id: str = Field(max_length=36)
    method: str = Field(default="fixed_schedule")
    model_id: str | None = Field(default=None, max_length=36)
    season_id: str | None = Field(default=None, max_length=20, description="Defaults to the first test season")
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    aquacrop: bool = True

    @field_validator("method")
    @classmethod
    def _method(cls, v: str) -> str:
        if v not in METHODS:
            raise ValueError(f"Unknown method; choose one of {sorted(METHODS)}")
        return v


class TrainingIn(_In):
    scenario_id: str = Field(max_length=36)
    preset: Literal["cpu_quick", "cpu_standard", "cpu_research"] = "cpu_quick"
    total_timesteps: int | None = Field(default=None, ge=256, le=3_000_000)
    seeds: list[int] | None = Field(default=None, max_length=10)
    hyperparameters: dict | None = None
    confirm_long_run: bool = Field(default=False, description="Required for presets above the quick smoke test")


class ExperimentIn(_In):
    scenario_id: str = Field(max_length=36)
    model_id: str | None = Field(default=None, max_length=36)
    name: str = Field(default="Baseline comparison", min_length=2, max_length=120)
    methods: list[str]
    reference_method: str = "fixed_schedule"
    split: Literal["validation", "test"] = "test"
    seeds: list[int] = Field(default_factory=lambda: [1, 2, 3])
    observation_budgets: list[int] = Field(default_factory=lambda: [10])
    sensor_noise_m3m3: list[float] = Field(default_factory=lambda: [0.02])
    sensor_mode: Literal["nominal", "missing", "biased", "stuck", "delayed"] = "nominal"
    uncertainty_threshold: float = Field(default=0.08, gt=0, le=1)
    aquacrop: bool = False


class ExportIn(_In):
    source_type: Literal["run", "experiment", "model"]
    source_id: str = Field(max_length=36)
    format: Literal["zip", "csv", "json", "html"] = "zip"
