"""Weather table validation, growing-season extraction and chronological splits.

Core schema (one row per day, canonical units):

    date (ISO YYYY-MM-DD), rain_mm (mm/day), eto_mm (FAO-56 reference ET, mm/day),
    tmin_c (°C), tmax_c (°C)

Nothing here imputes missing values: rows with NaN/Inf are quarantined and a
season that touches a quarantined or absent day is excluded, never filled in
from neighbouring (possibly future) observations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("date", "rain_mm", "eto_mm", "tmin_c", "tmax_c")
UNITS = {"rain_mm": "mm/day", "eto_mm": "mm/day (FAO-56 reference ET)", "tmin_c": "°C", "tmax_c": "°C"}
BOUNDS = {"rain_mm": (0.0, 500.0), "eto_mm": (0.0, 20.0), "tmin_c": (-60.0, 60.0), "tmax_c": (-60.0, 60.0)}
MAX_FILE_BYTES = 5_000_000
MAX_ROWS = 40_000


class WeatherValidationError(ValueError):
    def __init__(self, message: str, report: "ValidationReport | None" = None):
        super().__init__(message)
        self.report = report


@dataclass
class ValidationReport:
    rows: int = 0
    start: str | None = None
    end: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    quarantined_dates: list[str] = field(default_factory=list)
    missing_dates: int = 0
    missingness_pct: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {
            "rows": self.rows, "start": self.start, "end": self.end, "ok": self.ok,
            "errors": self.errors[:50], "warnings": self.warnings[:50],
            "quarantined_dates": self.quarantined_dates[:200], "quarantined_count": len(self.quarantined_dates),
            "missing_dates": self.missing_dates, "missingness_pct": self.missingness_pct,
        }


def validate_frame(raw: pd.DataFrame) -> tuple[pd.DataFrame, ValidationReport]:
    """Validate a raw weather table. Returns the clean frame (quarantined rows removed)."""
    report = ValidationReport()
    columns = [str(c).strip() for c in raw.columns]
    raw = raw.copy()
    raw.columns = columns
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        report.errors.append(f"Missing required column(s): {', '.join(missing)}. Required: {', '.join(REQUIRED_COLUMNS)}")
        raise WeatherValidationError(report.errors[0], report)
    frame = raw[list(REQUIRED_COLUMNS)].copy()
    report.rows = len(frame)
    if frame.empty:
        report.errors.append("Weather table is empty")
        raise WeatherValidationError(report.errors[0], report)
    if len(frame) > MAX_ROWS:
        report.errors.append(f"Too many rows ({len(frame)} > {MAX_ROWS})")
        raise WeatherValidationError(report.errors[0], report)
    parsed = pd.to_datetime(frame["date"].astype(str).str.strip(), format="%Y-%m-%d", errors="coerce")
    bad_dates = frame.loc[parsed.isna(), "date"].astype(str).tolist()
    if bad_dates:
        report.errors.append(f"{len(bad_dates)} malformed date(s), e.g. {bad_dates[:3]}; expected YYYY-MM-DD")
    frame["date"] = parsed
    duplicated = frame["date"][frame["date"].duplicated() & frame["date"].notna()]
    if len(duplicated):
        report.errors.append(f"{len(duplicated)} duplicated date(s), e.g. {[d.date().isoformat() for d in duplicated[:3]]}")
    for column in REQUIRED_COLUMNS[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    values = frame[list(REQUIRED_COLUMNS[1:])].to_numpy(dtype=float)
    finite = np.isfinite(values)
    for i, column in enumerate(REQUIRED_COLUMNS[1:]):
        report.missingness_pct[column] = round(100.0 * float((~finite[:, i]).mean()), 3)
    if report.errors:
        raise WeatherValidationError("; ".join(report.errors), report)
    if not frame["date"].is_monotonic_increasing:
        report.warnings.append("Rows were not in chronological order and have been sorted")
    frame = frame.sort_values("date").reset_index(drop=True)
    valid = np.isfinite(frame[list(REQUIRED_COLUMNS[1:])].to_numpy(dtype=float)).all(axis=1)
    quarantined = frame.loc[~valid, "date"]
    if len(quarantined):
        report.quarantined_dates = [d.date().isoformat() for d in quarantined]
        report.warnings.append(f"{len(quarantined)} row(s) with missing/NaN/Inf values quarantined (not imputed)")
    clean = frame[valid].copy()
    for column, (low, high) in BOUNDS.items():
        out = clean[(clean[column] < low) | (clean[column] > high)]
        if len(out):
            report.errors.append(f"{len(out)} value(s) of {column} outside physical bounds [{low}, {high}], e.g. {out['date'].iloc[0].date().isoformat()}")
    inverted = clean[clean["tmin_c"] > clean["tmax_c"]]
    if len(inverted):
        report.errors.append(f"{len(inverted)} day(s) with tmin_c > tmax_c, e.g. {inverted['date'].iloc[0].date().isoformat()}")
    if report.errors:
        raise WeatherValidationError("; ".join(report.errors), report)
    if clean.empty:
        report.errors.append("No valid rows after quarantine")
        raise WeatherValidationError(report.errors[0], report)
    span = (frame["date"].iloc[-1] - frame["date"].iloc[0]).days + 1
    report.missing_dates = int(span - len(frame))
    if report.missing_dates:
        report.warnings.append(f"{report.missing_dates} calendar day(s) absent; seasons touching them are excluded")
    report.start = clean["date"].iloc[0].date().isoformat()
    report.end = clean["date"].iloc[-1].date().isoformat()
    clean = clean.reset_index(drop=True)
    return clean, report


def read_weather_csv(path: Path | None = None, text: str | None = None) -> tuple[pd.DataFrame, ValidationReport]:
    """Parse and validate a weather CSV from disk or text (size-capped)."""
    if path is not None:
        path = Path(path)
        if not path.is_file():
            raise WeatherValidationError("Weather file not found")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise WeatherValidationError(f"Weather file exceeds {MAX_FILE_BYTES // 1_000_000} MB")
        text = path.read_text(encoding="utf-8-sig")
    if text is None or not text.strip():
        raise WeatherValidationError("Weather CSV is empty", ValidationReport(errors=["Weather CSV is empty"]))
    if len(text.encode()) > MAX_FILE_BYTES:
        raise WeatherValidationError(f"Weather file exceeds {MAX_FILE_BYTES // 1_000_000} MB")
    try:
        raw = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False, na_values=["", "NaN", "nan", "NA", "-999", "-999.0"])
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise WeatherValidationError(f"Malformed CSV: {exc}") from exc
    return validate_frame(raw)


def write_weather_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame[list(REQUIRED_COLUMNS)].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False, float_format="%.4f", lineterminator="\n")


@dataclass(frozen=True)
class Season:
    """One growing season of realized daily weather (hidden from the agent day by day)."""

    season_id: str
    dates: tuple[str, ...]
    rain_mm: np.ndarray
    eto_mm: np.ndarray
    tmin_c: np.ndarray
    tmax_c: np.ndarray

    def __len__(self) -> int:
        return len(self.dates)

    @property
    def start(self) -> str:
        return self.dates[0]


def extract_seasons(frame: pd.DataFrame, planting_mmdd: str, length: int) -> tuple[list[Season], list[str]]:
    """Cut one season per calendar year starting at ``planting_mmdd``.

    Returns (seasons in chronological order, human-readable skip reasons).
    """
    if length < 1:
        raise ValueError("Season length must be positive")
    indexed = frame.set_index(pd.to_datetime(frame["date"]))
    years = sorted(set(indexed.index.year))
    seasons, skipped = [], []
    for year in years:
        try:
            start = date.fromisoformat(f"{year}-{planting_mmdd}")
        except ValueError:
            skipped.append(f"{year}: invalid planting date")
            continue
        days = pd.date_range(start, start + timedelta(days=length - 1), freq="D")
        present = indexed.reindex(days)
        if present[list(REQUIRED_COLUMNS[1:])].isna().any().any():
            skipped.append(f"{year}: incomplete coverage for {start.isoformat()} + {length} days")
            continue
        seasons.append(Season(
            season_id=str(year),
            dates=tuple(d.date().isoformat() for d in days),
            rain_mm=present["rain_mm"].to_numpy(dtype=float),
            eto_mm=present["eto_mm"].to_numpy(dtype=float),
            tmin_c=present["tmin_c"].to_numpy(dtype=float),
            tmax_c=present["tmax_c"].to_numpy(dtype=float),
        ))
    return seasons, skipped


@dataclass(frozen=True)
class SeasonSplit:
    train: tuple[str, ...]
    validation: tuple[str, ...]
    test: tuple[str, ...]
    rule: str

    def as_dict(self) -> dict:
        return {"train": list(self.train), "validation": list(self.validation), "test": list(self.test), "rule": self.rule}

    def ids(self, split: str) -> tuple[str, ...]:
        if split not in {"train", "validation", "test"}:
            raise ValueError("split must be train, validation or test")
        return getattr(self, split)


def chronological_split(season_ids: list[str], train_fraction: float = 0.6, validation_fraction: float = 0.2) -> SeasonSplit:
    """Whole-season chronological split (never split by day, never shuffle)."""
    ids = sorted(season_ids)
    n = len(ids)
    if n == 0:
        return SeasonSplit((), (), (), "no complete seasons")
    if n == 1:
        return SeasonSplit((), (), tuple(ids), "single season: evaluation only, training unavailable")
    if n == 2:
        return SeasonSplit((ids[0],), (), (ids[1],), "two seasons: earliest train, latest test, no validation")
    n_val = max(1, round(validation_fraction * n))
    n_test = max(1, round((1 - train_fraction - validation_fraction) * n))
    n_train = n - n_val - n_test
    if n_train < 1:
        n_train, n_val, n_test = 1, 1, n - 2
    return SeasonSplit(tuple(ids[:n_train]), tuple(ids[n_train:n_train + n_val]), tuple(ids[n_train + n_val:]),
                       f"chronological {n_train}/{n_val}/{n_test} whole-season split")


def preview_frame(frame: pd.DataFrame, max_points: int = 400) -> list[dict]:
    """Evenly decimated series for charts; rows are copied, never interpolated."""
    if len(frame) <= max_points:
        sample = frame
    else:
        index = np.unique(np.linspace(0, len(frame) - 1, max_points).round().astype(int))
        sample = frame.iloc[index]
    out = sample.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out[list(REQUIRED_COLUMNS)].round(4).to_dict(orient="records")
