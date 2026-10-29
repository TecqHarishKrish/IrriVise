"""Deterministic SYNTHETIC weather generator for offline demonstrations.

The output is labelled "synthetic demonstration" everywhere. It is not
historical weather and not a field measurement. It mimics a semi-arid
south-Indian (Tamil Nadu plains) rainfall regime qualitatively: a modest
south-west monsoon (Jun–Sep), a stronger north-east monsoon (Oct–Dec) and
year-to-year wet/dry variability.

Method (documented so it can be regenerated and criticised):
* rain occurrence: first-order two-state Markov chain with monthly wet-day
  probabilities; amounts: gamma(shape 0.75) scaled to monthly wet-day means;
  a lognormal year factor creates dry and wet years;
* temperature: seasonal harmonics plus AR(1) noise, cooler on wet days;
* reference ET: FAO-56 Hargreaves equation (eq. 52) with extraterrestrial
  radiation Ra from FAO-56 eq. 21 for the configured latitude.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import acos, cos, pi, sin, tan

import numpy as np
import pandas as pd

GENERATOR_VERSION = "synthetic-tn-v1"
# Monthly wet-day probability and mean wet-day rainfall (mm), Jan..Dec.
P_WET = (0.05, 0.05, 0.06, 0.12, 0.17, 0.20, 0.24, 0.28, 0.32, 0.45, 0.45, 0.25)
MEAN_WET_MM = (6.0, 6.0, 7.0, 9.0, 11.0, 9.0, 9.5, 10.0, 12.0, 14.0, 14.0, 11.0)


def extraterrestrial_radiation(day_of_year: int, latitude: float) -> float:
    """FAO-56 eq. 21, MJ m-2 day-1."""
    phi = latitude * pi / 180
    dr = 1 + 0.033 * cos(2 * pi * day_of_year / 365)
    decl = 0.409 * sin(2 * pi * day_of_year / 365 - 1.39)
    ws = acos(max(-1.0, min(1.0, -tan(phi) * tan(decl))))
    return 24 * 60 / pi * 0.0820 * dr * (ws * sin(phi) * sin(decl) + cos(phi) * cos(decl) * sin(ws))


def hargreaves_eto(tmin: float, tmax: float, ra_mj: float) -> float:
    """FAO-56 eq. 52 (Ra converted to mm/day equivalent with 0.408)."""
    return max(0.0, 0.0023 * ((tmax + tmin) / 2 + 17.8) * np.sqrt(max(0.0, tmax - tmin)) * 0.408 * ra_mj)


def generate_synthetic_weather(start_year: int = 2004, years: int = 20, latitude: float = 10.79, seed: int = 42) -> pd.DataFrame:
    if not 1 <= years <= 60:
        raise ValueError("years must be 1..60")
    rng = np.random.default_rng(seed)
    rows = []
    wet_yesterday = False
    t_anom = 0.0
    for year in range(start_year, start_year + years):
        year_factor = float(np.exp(rng.normal(0.0, 0.32)))
        occurrence_shift = float(rng.normal(0.0, 0.04))
        day = date(year, 1, 1)
        while day.year == year:
            month = day.month - 1
            p = min(0.95, max(0.01, P_WET[month] + occurrence_shift))
            # Persistence: wet days are more likely after wet days.
            p_today = min(0.95, p + 0.18) if wet_yesterday else max(0.01, p - 0.05)
            wet = rng.random() < p_today
            rain = float(rng.gamma(0.75, MEAN_WET_MM[month] * year_factor / 0.75)) if wet else 0.0
            rain = min(rain, 250.0)
            doy = day.timetuple().tm_yday
            t_anom = 0.7 * t_anom + rng.normal(0.0, 0.8)
            seasonal = sin(2 * pi * (doy - 80) / 365)
            tmax = 33.5 + 3.0 * seasonal + t_anom - (2.0 if wet else 0.0)
            tmin = 23.0 + 2.2 * seasonal + 0.5 * t_anom + (0.5 if wet else 0.0)
            tmin = min(tmin, tmax - 2.0)
            eto = hargreaves_eto(tmin, tmax, extraterrestrial_radiation(doy, latitude)) * (0.85 if wet else 1.0)
            rows.append((day.isoformat(), round(rain, 2), round(eto, 2), round(tmin, 2), round(tmax, 2)))
            wet_yesterday = wet
            day += timedelta(days=1)
    return pd.DataFrame(rows, columns=["date", "rain_mm", "eto_mm", "tmin_c", "tmax_c"])
