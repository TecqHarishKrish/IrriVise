"""Weather CSV validation and file provenance."""
import csv
import hashlib
from datetime import date, timedelta
from pathlib import Path
from .science import Weather


def load_weather(path: Path) -> list[Weather]:
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise ValueError("Weather file missing or exceeds 5 MB")
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or []) != {"date", "rain_mm", "eto_mm", "tmin_c", "tmax_c"}:
            raise ValueError("Weather CSV requires date,rain_mm,eto_mm,tmin_c,tmax_c")
        rows = []
        previous = None
        for raw in reader:
            day = date.fromisoformat(raw["date"])
            if previous and day != previous + timedelta(days=1):
                raise ValueError("Weather dates must be daily, unique, and ascending")
            rows.append(Weather(raw["date"], *(float(raw[k]) for k in ("rain_mm", "eto_mm", "tmin_c", "tmax_c"))))
            previous = day
    if not rows:
        raise ValueError("Weather CSV is empty")
    return rows


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
