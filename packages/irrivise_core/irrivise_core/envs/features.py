"""Policy observation vector (fixed shape, documented, physically normalised).

Normalisation uses fixed physical ranges (not statistics of any dataset), so
no validation/test information can enter the scaling. Every feature is
clipped to [0, 1]. Source of every feature is the AgentView — never the
hidden reference farm, never realized future weather.
"""
from __future__ import annotations

import numpy as np

from ..simulation.world import AgentView

FEATURE_SPEC_VERSION = "irrivise-obs-v1"
FEATURES: tuple[tuple[str, str], ...] = (
    ("depletion_fraction", "estimated root-zone depletion Dr/TAW (twin), /1.0"),
    ("depletion_std_fraction", "twin storage std / TAW, ×4"),
    ("relative_storage", "(mean θ − WP_nominal) / (SAT − WP), twin"),
    ("ks_estimate", "twin mean water-stress coefficient Ks"),
    ("season_progress", "day / season length"),
    ("kc_normalised", "crop coefficient Kc / 1.3"),
    ("ky_normalised", "stage yield-response factor Ky / 2"),
    ("rain_yesterday", "observed rain day-1, /50 mm"),
    ("rain_last3", "observed rain sum days-3..-1, /100 mm"),
    ("forecast_rain_next3", "forecast expected rain next 3 days, /50 mm"),
    ("forecast_eto_next3", "forecast mean ET0 next 3 days, /10 mm"),
    ("water_remaining_fraction", "remaining seasonal water / seasonal budget"),
    ("water_pace", "remaining water / (remaining days × daily max)"),
    ("observations_remaining_fraction", "remaining readings / observation budget"),
    ("days_since_observation", "days since last reading, /30"),
    ("root_depth_fraction", "root depth / 1.5 m"),
)
N_FEATURES = len(FEATURES)


def agent_features(view: AgentView, soil_wp: float, soil_sat: float) -> np.ndarray:
    b = view.belief
    z = b.root_depth_m
    taw = max(b.taw_mm, 1e-6)
    rain = view.observed_rain_mm
    f = view.forecast
    days_left = max(1, view.season_length - view.day)
    values = [
        b.depletion_fraction,
        4.0 * b.std_storage_mm / taw,
        (b.mean_theta - soil_wp) / (soil_sat - soil_wp),
        b.ks_estimate,
        view.day / view.season_length,
        view.kc / 1.3,
        view.ky / 2.0,
        (rain[-1] if rain else 0.0) / 50.0,
        sum(rain[-3:]) / 100.0,
        float(np.sum(f.rain_mm[:3])) / 50.0,
        float(np.mean(f.eto_mm[:3])) / 10.0,
        view.remaining_water_mm / view.seasonal_budget_mm if view.seasonal_budget_mm > 0 else 0.0,
        view.remaining_water_mm / (days_left * view.daily_max_mm) if view.daily_max_mm > 0 else 0.0,
        view.remaining_observations / view.observation_budget if view.observation_budget > 0 else 0.0,
        min(30, b.days_since_observation) / 30.0,
        z / 1.5,
    ]
    vector = np.clip(np.asarray(values, dtype=np.float32), 0.0, 1.0)
    if not np.all(np.isfinite(vector)):
        raise FloatingPointError("Non-finite policy observation")
    return vector
