"""Bounded NASA POWER daily ingestion with FAO-56 reference ET calculation.

Only the fixed NASA POWER endpoint is contacted. Native NASA values and units
are preserved in the cached response and manifest. UTC/LST denotes POWER's
daily time standard, not the location's civil time zone.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, timedelta
from math import acos, cos, exp, isfinite, pi, radians, sin, sqrt, tan
from pathlib import Path

import httpx

from .data import checksum, load_weather
from .science import Weather

ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = ("T2M_MAX", "T2M_MIN", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN", "WS2M", "RH2M")
EXPECTED_UNITS = {"T2M_MAX": "C", "T2M_MIN": "C", "PRECTOTCORR": "mm/day", "ALLSKY_SFC_SW_DWN": "MJ/m^2/day", "WS2M": "m/s", "RH2M": "%"}


def fao56_eto(day: date, latitude: float, elevation_m: float, tmin_c: float, tmax_c: float, radiation_mj_m2_day: float, wind_m_s: float, rh_mean_pct: float | None = None, rh_min_pct: float | None = None, rh_max_pct: float | None = None) -> float:
    """Daily FAO-56 Penman-Monteith ETo, with G=0 and 2-m wind speed.

    NASA POWER supplies RH2M mean. With only mean RH, actual vapour pressure is
    approximated as RHmean/100 times mean saturation vapour pressure; FAO-56
    prefers RHmax/RHmin when available. The inputs must use NASA's reported
    C, MJ/m²/day, m/s and percent units.
    """
    values = (latitude, elevation_m, tmin_c, tmax_c, radiation_mj_m2_day, wind_m_s)
    if not all(isfinite(x) for x in values) or not -90 <= latitude <= 90 or not -500 <= elevation_m <= 9000 or tmin_c > tmax_c or radiation_mj_m2_day < 0 or wind_m_s < 0:
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
    ea = (es_min * rh_max_pct / 100 + es_max * rh_min_pct / 100) / 2 if rh_min_pct is not None and rh_max_pct is not None else es * rh_mean_pct / 100
    delta = 4098 * saturation(tmean) / (tmean + 237.3) ** 2
    pressure = 101.3 * ((293 - 0.0065 * elevation_m) / 293) ** 5.26
    gamma = 0.000665 * pressure
    julian = day.timetuple().tm_yday
    phi = radians(latitude)
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


def parse_power(payload: dict, start: date, end: date, latitude: float, time_standard: str) -> list[Weather]:
    header = payload.get("header", {})
    if header.get("time_standard") != time_standard:
        raise ValueError("NASA POWER time standard mismatch")
    parameter_meta = payload.get("parameters", {})
    native = payload.get("properties", {}).get("parameter", {})
    for name, unit in EXPECTED_UNITS.items():
        if parameter_meta.get(name, {}).get("units") != unit or not isinstance(native.get(name), dict):
            raise ValueError(f"NASA POWER parameter or unit mismatch: {name}")
    coordinates = payload.get("geometry", {}).get("coordinates", [])
    if len(coordinates) < 3 or not isfinite(float(coordinates[2])):
        raise ValueError("NASA POWER elevation is missing")
    elevation = float(coordinates[2])
    missing = float(header.get("fill_value", -999))
    rows = []
    day = start
    while day <= end:
        key = day.strftime("%Y%m%d")
        raw = []
        for parameter in PARAMETERS:
            value = native[parameter].get(key)
            if value is None or not isfinite(float(value)) or float(value) == missing:
                raise ValueError(f"NASA POWER missing {parameter} on {key}")
            raw.append(float(value))
        tmax, tmin, rain, radiation, wind, humidity = raw
        eto = fao56_eto(day, latitude, elevation, tmin, tmax, radiation, wind, rh_mean_pct=humidity)
        rows.append(Weather(day.isoformat(), rain, eto, tmin, tmax))
        day += timedelta(days=1)
    return rows


def download_power(latitude: float, longitude: float, start: date, end: date, time_standard: str, root: Path, client: httpx.Client | None = None) -> dict:
    if not all(isfinite(x) for x in (latitude, longitude)) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or time_standard not in {"UTC", "LST"} or end < start or (end - start).days > 730 or end >= date.today():
        raise ValueError("Invalid coordinates, time standard, or date span (maximum 731 past days)")
    query = {"parameters": ",".join(PARAMETERS), "community": "AG", "latitude": latitude, "longitude": longitude, "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"), "format": "JSON", "time-standard": time_standard}
    key = hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()
    raw_path = root / "data/raw" / f"nasa-{key}.json"
    csv_path = root / "data/processed" / f"nasa-{key}.csv"
    manifest_path = root / "data/manifests" / f"nasa-{key}.json"
    if raw_path.exists():
        payload = json.loads(raw_path.read_text())
    else:
        owns_client = client is None
        client = client or httpx.Client(timeout=45, follow_redirects=False)
        try:
            response = client.get(ENDPOINT, params=query)
            response.raise_for_status()
            if len(response.content) > 20_000_000:
                raise ValueError("NASA POWER response exceeds 20 MB")
            payload = response.json()
        finally:
            if owns_client:
                client.close()
    rows = parse_power(payload, start, end, latitude, time_standard)
    if not raw_path.exists():
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(payload))
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "rain_mm", "eto_mm", "tmin_c", "tmax_c"])
        for row in rows:
            writer.writerow([row.date, row.rain_mm, round(row.eto_mm, 4), row.tmin_c, row.tmax_c])
    load_weather(csv_path)
    manifest = {"id": key, "source": "nasa_power", "source_url": ENDPOINT, "query": query, "days": len(rows), "start": rows[0].date, "end": rows[-1].date, "time_standard": time_standard, "native_units": EXPECTED_UNITS, "eto_method": "FAO-56 Penman-Monteith; RHmean approximation; NASA POWER elevation", "checksum_sha256": checksum(csv_path), "processed_path": str(csv_path.relative_to(root)), "raw_path": str(raw_path.relative_to(root)), "note": "Historical gridded weather, not measured farm outcomes; UTC/LST is not civil time"}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest
