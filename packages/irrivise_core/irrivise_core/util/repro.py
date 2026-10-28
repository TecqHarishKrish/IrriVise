"""Reproducibility helpers: seeded generators, canonical hashing, environment capture."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np


def rng(*keys: int | str) -> np.random.Generator:
    """Independent, deterministic generator derived from a tuple of keys.

    Using separate streams per purpose (hidden farm, twin, sensor, ...) keeps
    paired experiments comparable: changing one consumer never shifts another's
    random draws (common random numbers).
    """
    material = "|".join(str(k) for k in keys).encode()
    seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "little")
    return np.random.default_rng(seed)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


_PACKAGES = ("numpy", "pandas", "scipy", "gymnasium", "stable-baselines3", "torch", "aquacrop", "fastapi", "sqlalchemy", "pydantic")


def package_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for name in _PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions


def code_revision(root: Path | None = None) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root or Path(__file__).resolve().parents[4], capture_output=True, text=True, timeout=5, check=False)
        revision = out.stdout.strip()
        if not revision:
            return "unknown"
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root or Path(__file__).resolve().parents[4], capture_output=True, text=True, timeout=5, check=False).stdout.strip()
        return revision + ("+dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"
