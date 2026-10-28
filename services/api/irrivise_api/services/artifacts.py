"""Safe artifact paths: every path is derived from generated ids and verified under the data root."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from ..config import get_settings
from ..errors import ApiError

_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def safe_join(*parts: str) -> Path:
    root = get_settings().data_root.resolve()
    for part in parts:
        if not part or ".." in part.replace("\\", "/").split("/") or part.startswith(("/", "\\")):
            raise ApiError(400, "unsafe_path", "Unsafe artifact path")
    path = root.joinpath(*parts).resolve()
    if path != root and root not in path.parents:
        raise ApiError(400, "unsafe_path", "Unsafe artifact path")
    return path


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(get_settings().data_root.resolve()))


def check_id(value: str) -> str:
    if not _ID.fullmatch(value or ""):
        raise ApiError(400, "invalid_id", "Invalid identifier")
    return value


def run_dir(run_id: str) -> Path:
    return safe_join("artifacts", "runs", check_id(run_id))


def experiment_dir(experiment_id: str) -> Path:
    return safe_join("artifacts", "experiments", check_id(experiment_id))


def model_dir() -> Path:
    return safe_join("artifacts", "models")


def export_dir() -> Path:
    return safe_join("artifacts", "exports")


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=1, default=str))
    tmp.replace(path)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    tmp.replace(path)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def disk_usage_bytes() -> int:
    root = get_settings().data_root / "artifacts"
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) if root.exists() else 0
