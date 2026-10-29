"""Runtime settings (environment variables, all optional; safe local defaults)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    data_root: Path = field(default_factory=lambda: Path(os.getenv("IRRIVISE_DATA_ROOT", str(REPO_ROOT))).resolve())
    cors_origins: tuple[str, ...] = field(default_factory=lambda: tuple(o.strip() for o in os.getenv(
        "IRRIVISE_CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173").split(",") if o.strip()))
    max_upload_bytes: int = field(default_factory=lambda: _int("IRRIVISE_MAX_UPLOAD_BYTES", 5_000_000))
    max_queued_jobs: int = field(default_factory=lambda: _int("IRRIVISE_MAX_QUEUED_JOBS", 25))
    max_parallel_training: int = field(default_factory=lambda: _int("IRRIVISE_MAX_PARALLEL_TRAINING", 1))
    max_parallel_other: int = field(default_factory=lambda: _int("IRRIVISE_MAX_PARALLEL_JOBS", 2))
    heartbeat_timeout_s: int = field(default_factory=lambda: _int("IRRIVISE_HEARTBEAT_TIMEOUT_S", 60))
    cancel_grace_s: int = field(default_factory=lambda: _int("IRRIVISE_CANCEL_GRACE_S", 30))
    storage_quota_bytes: int = field(default_factory=lambda: _int("IRRIVISE_STORAGE_QUOTA_BYTES", 5_000_000_000))

    @property
    def database_path(self) -> Path:
        override = os.getenv("IRRIVISE_DATABASE")
        return Path(override).resolve() if override else self.data_root / "data" / "irrivise.sqlite3"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    def path(self, *parts: str) -> Path:
        return self.data_root.joinpath(*parts)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
