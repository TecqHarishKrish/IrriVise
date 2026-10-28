"""Load versioned YAML profiles from the repository ``configs/`` directory."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

from .schemas import CaratConfig, CropProfile, ScenarioConfig, SoilProfile, TrainingConfig

_NAME = re.compile(r"^[a-z0-9_]{1,40}$")


def config_dir() -> Path:
    override = os.getenv("IRRIVISE_CONFIG_DIR")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[4] / "configs"


def _load(kind: str, name: str) -> dict:
    if not _NAME.fullmatch(name):
        raise ValueError(f"Invalid {kind} profile name")
    path = config_dir() / kind / f"{name}.yaml"
    if not path.is_file():
        raise ValueError(f"Unknown {kind} profile: {name}")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Malformed {kind} profile: {name}")
    return data


def list_profiles(kind: str) -> list[str]:
    directory = config_dir() / kind
    return sorted(p.stem for p in directory.glob("*.yaml")) if directory.is_dir() else []


@lru_cache(maxsize=32)
def load_crop(name: str = "maize") -> CropProfile:
    return CropProfile(**_load("crops", name))


@lru_cache(maxsize=32)
def load_soil(name: str = "sandy_loam") -> SoilProfile:
    return SoilProfile(**_load("soils", name))


@lru_cache(maxsize=8)
def load_carat(name: str = "default") -> CaratConfig:
    return CaratConfig(**_load("carat", name))


def load_training(preset: str = "cpu_quick") -> TrainingConfig:
    return TrainingConfig(**_load("training", preset))


def default_scenario(**overrides) -> ScenarioConfig:
    """Default maize / sandy-loam scenario used by the offline demonstration."""
    base = {"crop": load_crop("maize"), "soil": load_soil("sandy_loam"), "carat": load_carat("default")}
    base.update(overrides)
    return ScenarioConfig(**base)
