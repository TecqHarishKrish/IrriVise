"""Bounded NASA POWER daily point ingestion with FAO-56 reference ET.

Only the fixed official endpoint is contacted, with bounded retries, a timeout,
a response-size cap and an on-disk cache keyed by the exact query. Native NASA
values and units are preserved in the raw cache and the manifest. ``UTC``/``LST``
is POWER's daily time standard, not the location's civil time zone.

API reference: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date, timedelta
from math import acos, cos, exp, isfinite, pi, sin, sqrt, tan
from pathlib import Path
from typing import Callable

import httpx
import pandas as pd

from .weather import validate_frame, write_weather_csv
from ..util.repro import sha256_file

ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = ("T2M_MAX", "T2M_MIN", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN", "WS2M", "RH2M")
EXPECTED_UNITS = {"T2M_MAX": "C", "T2M_MIN": "C", "PRECTOTCORR": "mm/day", "ALLSKY_SFC_SW_DWN": "MJ/m^2/day", "WS2M": "m/s", "RH2M": "%"}
MAX_SPAN_DAYS = 25 * 366
MAX_RESPONSE_BYTES = 30_000_000
LICENSE = "NASA POWER data are freely available; cite the NASA Langley Research Center POWER Project (https://power.larc.nasa.gov)."


class PowerError(RuntimeError):
    pass


def fao56_eto(day: date, latitude: float, elevation_m: float, tmin_c: float, tmax_c: float, radiation_mj_m2_day: float,
              wind_m_s: float, rh_mean_pct: float | None = None, rh_min_pct: float | None = None, rh_max_pct: float | None = None) -> float:
    """Daily FAO-56 Penman-Monteith reference ET (mm/day), G = 0, 2 m wind.

    NASA POWER supplies RH2M (daily mean). With only mean RH, actual vapour
    pressure is approximated as RHmean/100 × mean saturation vapour pressure
    (FAO-56 eq. 19); FAO-56 prefers RHmax/RHmin when available.
    """
    values = (latitude, elevation_m, tmin_c, tmax_c, radiation_mj_m2_day, wind_m_s)
    if not all(isfinite(x) for x in values) or not -90 <= latitude <= 90 or not -500 <= elevation_m <= 9000 \
            or tmin_c > tmax_c or radiation_mj_m2_day < 0 or wind_m_s < 0:
        raise ValueError("Invalid FAO-56 meteorological inputs")
    if rh_mean_pct is None and (rh_min_pct is None or rh_max_pct is None):
        raise ValueError("Relative humidity is required")
    humidities = [x for x in (rh_mean_pct, rh_min_pct, rh_max_pct) if x is not None]
    if any(not isfinite(x) or not 0 <= x <= 100 for x in humidities):
        raise ValueError("Relative humidity must be 0–100%")

    def saturation(t: float) -> float:
        return 0.6108 * exp(17.27 * t / (t + 237.3))

    tmean = (tmin_c + tmax_c) / 2
    es_max, es_min = saturation(tmax_c), saturation(tmin_c)
    es = (es_max + es_min) / 2
    if rh_min_pct is not None and rh_max_pct is not None:
        ea = (es_min * rh_max_pct / 100 + es_max * rh_min_pct / 100) / 2
    else:
        ea = es * rh_mean_pct / 100  # type: ignore[operator]
    delta = 4098 * saturation(tmean) / (tmean + 237.3) ** 2
    pressure = 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.26
    gamma = 0.000665 * pressure
    julian = day.timetuple().tm_yday
    phi = latitude * pi / 180
    dr = 1 + 0.033 * cos(2 * pi * julian / 365)
    declination = 0.409 * sin(2 * pi * julian / 365 - 1.39)
    sunset = acos(max(-1.0, min(1.0, -tan(phi) * tan(declination))))
    ra = 24 * 60 / pi * 0.0820 * dr * (sunset * sin(phi) * sin(declination) + cos(phi) * cos(declination) * sin(sunset))
    rso = (0.75 + 2e-5 * elevation_m) * ra
    cloud_ratio = max(0.3, min(1.0, radiation_mj_m2_day / rso)) if rso > 0 else 0.3
    rnl = 4.903e-9 * ((tmax_c + 273.16) ** 4 + (tmin_c + 273.16) ** 4) / 2 * (0.34 - 0.14 * sqrt(max(0.0, ea))) * (1.35 * cloud_ratio - 0.35)
    rn = 0.77 * radiation_mj_m2_day - rnl
    numerator = 0.408 * delta * rn + gamma * 900 / (tmean + 273) * wind_m_s * max(0.0, es - ea)
    denominator = delta + gamma * (1 + 0.34 * wind_m_s)
    return max(0.0, numerator / denominator)


def build_query(latitude: float, longitude: float, start: date, end: date, time_standard: str) -> dict:
    if not all(isfinite(x) for x in (latitude, longitude)) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Latitude must be in [-90, 90] and longitude in [-180, 180]")
    if time_standard not in {"UTC", "LST"}:
        raise ValueError("time_standard must be UTC or LST")
    if end < start or (end - start).days > MAX_SPAN_DAYS or end >= date.today() or start < date(1981, 1, 1):
        raise ValueError(f"Date range must be past days from 1981-01-01 and at most {MAX_SPAN_DAYS} days long")
    return {"parameters": ",".join(PARAMETERS), "community": "AG", "latitude": round(latitude, 4), "longitude": round(longitude, 4),
            "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"), "format": "JSON", "time-standard": time_standard}


def parse_power(payload: dict, start: date, end: date, latitude: float, time_standard: str) -> tuple[pd.DataFrame, dict]:
    """Convert a POWER JSON payload into the core schema. Fill values become NaN (quarantined)."""
    header = payload.get("header", {})
    if str(header.get("time_standard", "")).upper() != time_standard:
        raise PowerError("NASA POWER time standard mismatch")
    parameter_meta = payload.get("parameters", {})
    native = payload.get("properties", {}).get("parameter", {})
    for name, unit in EXPECTED_UNITS.items():
        if parameter_meta.get(name, {}).get("units") != unit or not isinstance(native.get(name), dict):
            raise PowerError(f"NASA POWER parameter or unit mismatch: {name}")
    coordinates = payload.get("geometry", {}).get("coordinates", [])
    if len(coordinates) < 3 or not isfinite(float(coordinates[2])):
        raise PowerError("NASA POWER elevation is missing")
    elevation = float(coordinates[2])
    fill = float(header.get("fill_value", -999))
    rows, fill_count = [], 0
    day = start
    while day <= end:
        key = day.strftime("%Y%m%d")
        raw = []
        for parameter in PARAMETERS:
            value = native[parameter].get(key)
            value = float("nan") if value is None else float(value)
            if not isfinite(value) or value == fill:
                value = float("nan")
                fill_count += 1
            raw.append(value)
        tmax, tmin, rain, radiation, wind, humidity = raw
        if all(isfinite(v) for v in raw):
            eto = fao56_eto(day, latitude, elevation, tmin, tmax, radiation, wind, rh_mean_pct=humidity)
        else:
            eto = float("nan")
        rows.append({"date": day.isoformat(), "rain_mm": rain, "eto_mm": eto, "tmin_c": tmin, "tmax_c": tmax})
        day += timedelta(days=1)
    meta = {"elevation_m": elevation, "fill_value": fill, "fill_value_count": fill_count}
    return pd.DataFrame(rows), meta


def fetch_power(query: dict, client: httpx.Client | None = None, retries: int = 3, timeout_s: float = 60.0,
                sleep: Callable[[float], None] = time.sleep) -> dict:
    """GET with bounded retries/backoff for network errors, 429 and 5xx."""
    owns = client is None
    client = client or httpx.Client(timeout=timeout_s, follow_redirects=False)
    last_error = "unknown error"
    try:
        for attempt in range(retries):
            try:
                response = client.get(ENDPOINT, params=query)
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = f"HTTP {response.status_code} from NASA POWER"
                else:
                    if response.status_code >= 400:
                        raise PowerError(f"NASA POWER rejected the request (HTTP {response.status_code})")
                    if len(response.content) > MAX_RESPONSE_BYTES:
                        raise PowerError("NASA POWER response exceeds size cap")
                    return response.json()
            except httpx.HTTPError as exc:
                last_error = f"Network error contacting NASA POWER: {type(exc).__name__}"
            if attempt + 1 < retries:
                sleep(2 ** attempt)
        raise PowerError(f"{last_error} after {retries} attempt(s). Use cached data or the synthetic sample dataset.")
    finally:
        if owns:
            client.close()


def download_power(latitude: float, longitude: float, start: date, end: date, time_standard: str, root: Path,
                   client: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep) -> dict:
    """Fetch (or reuse cache), validate, convert and persist. Returns a manifest dict."""
    query = build_query(latitude, longitude, start, end, time_standard)
    key = hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()[:32]
    raw_path = root / "data/raw" / f"nasa-{key}.json"
    csv_path = root / "data/processed" / f"nasa-{key}.csv"
    cached = raw_path.exists()
    payload = json.loads(raw_path.read_text()) if cached else fetch_power(query, client=client, sleep=sleep)
    frame, meta = parse_power(payload, start, end, latitude, time_standard)
    clean, report = validate_frame(frame)
    if not cached:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(payload))
    write_weather_csv(clean, csv_path)
    return {
        "cache_key": key, "source": "nasa_power", "source_url": ENDPOINT, "query": query, "cache_hit": cached,
        "rows": len(clean), "start": report.start, "end": report.end, "time_standard": time_standard,
        "native_units": EXPECTED_UNITS, "elevation_m": meta["elevation_m"], "fill_values_quarantined": meta["fill_value_count"],
        "eto_method": "FAO-56 Penman-Monteith (G=0); RHmean approximation for ea; NASA POWER elevation",
        "checksum_sha256": sha256_file(csv_path), "processed_path": str(csv_path.relative_to(root)),
        "raw_path": str(raw_path.relative_to(root)), "validation": report.as_dict(), "license": LICENSE,
        "note": "Historical gridded reanalysis/satellite weather, not on-farm measurements; UTC/LST is not civil time.",
    }
