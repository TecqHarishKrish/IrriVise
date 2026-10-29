"""Weather forecasts built only from legitimate information.

The forecaster never sees the season being decided. It combines
(a) day-of-season climatology fitted on TRAINING seasons only, and
(b) persistence of weather the agent has already observed this season.
Realized future weather is never copied into a forecast. When no training
climatology exists (or the forecast is declared missing) a documented
past-only fallback with lower confidence is used.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..data.weather import Season

DEFAULT_ETO_MM = 5.0  # fallback when no past observations or climatology exist


@dataclass(frozen=True)
class Forecast:
    rain_mm: np.ndarray        # expected rainfall per lead day (mm/day)
    eto_mm: np.ndarray         # expected reference ET per lead day (mm/day)
    wet_probability: np.ndarray
    source: str
    confidence: str            # "climatology+persistence" | "low"

    def as_dict(self) -> dict:
        return {"rain_mm": [round(float(x), 3) for x in self.rain_mm], "eto_mm": [round(float(x), 3) for x in self.eto_mm],
                "wet_probability": [round(float(x), 3) for x in self.wet_probability], "source": self.source, "confidence": self.confidence}


class ClimatologyForecaster:
    def __init__(self, training_seasons: list[Season] | None = None, window_days: int = 10, available: bool = True):
        self.available = available
        self.training_ids = tuple(s.season_id for s in training_seasons or [])
        self._clim = None
        if training_seasons:
            length = min(len(s) for s in training_seasons)
            rain = np.stack([s.rain_mm[:length] for s in training_seasons])
            eto = np.stack([s.eto_mm[:length] for s in training_seasons])
            wet = rain > 0.5
            p_wet, mean_rain, mean_eto = [], [], []
            for d in range(length):
                lo, hi = max(0, d - window_days), min(length, d + window_days + 1)
                p_wet.append(float(wet[:, lo:hi].mean()))
                mean_rain.append(float(rain[:, lo:hi].mean()))
                mean_eto.append(float(eto[:, lo:hi].mean()))
            self._clim = (np.array(p_wet), np.array(mean_rain), np.array(mean_eto))

    def forecast(self, day: int, observed_rain: list[float], observed_eto: list[float], horizon: int) -> Forecast:
        """Forecast days ``day .. day+horizon-1`` using only observations from days < ``day``."""
        if len(observed_rain) != day or len(observed_eto) != day:
            raise ValueError("Forecast may only use observations from days before the decision day")
        recent_eto = float(np.mean(observed_eto[-3:])) if observed_eto else None
        recent_rain = float(np.mean(observed_rain[-14:])) if observed_rain else 0.0
        leads = np.arange(horizon)
        if self._clim is not None and self.available:
            p_wet, mean_rain, mean_eto = self._clim
            idx = np.minimum(day + leads, len(p_wet) - 1)
            clim_eto = mean_eto[idx]
            persistence_weight = 0.7 ** (leads + 1)
            eto = clim_eto if recent_eto is None else persistence_weight * recent_eto + (1 - persistence_weight) * clim_eto
            return Forecast(mean_rain[idx].copy(), eto, p_wet[idx].copy(),
                            f"climatology of {len(self.training_ids)} training season(s) + ET0 persistence", "climatology+persistence")
        eto_value = recent_eto if recent_eto is not None else DEFAULT_ETO_MM
        return Forecast(np.full(horizon, recent_rain), np.full(horizon, eto_value), np.full(horizon, np.nan),
                        "past-only persistence fallback (no training climatology or forecast unavailable)", "low")
