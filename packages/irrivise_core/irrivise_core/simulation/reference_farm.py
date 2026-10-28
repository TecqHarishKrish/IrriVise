"""Hidden simulated reference farm (the ground truth of a simulation).

Only three consumers may read its state:
* the environment reward / episode loop (scalar consequences of an action),
* :class:`~irrivise_core.simulation.sensor.SensorGateway` (noisy, budgeted reads),
* the post-run evaluator (``evaluation_record``).

Policies, the estimated twin, CARAT and the risk manager never receive this
object. Its soil parameters are a hidden random draw around the nominal soil
profile, so the twin faces genuine parameter uncertainty (model mismatch).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config.schemas import ScenarioConfig
from . import water_balance as wb


def draw_soil_parameters(scenario: ScenarioConfig, rng: np.random.Generator, size: int | None = None) -> dict[str, np.ndarray]:
    """Sample plausible soil/crop parameters from the scenario prior (shared by farm and twin)."""
    soil, u = scenario.soil, scenario.uncertainty
    n = 1 if size is None else size
    rel = u.soil_param_rel_std
    wp = soil.theta_wp * np.exp(rng.normal(0, rel, n))
    fc = soil.theta_fc * np.exp(rng.normal(0, rel, n))
    sat = soil.theta_sat * np.exp(rng.normal(0, rel / 2, n))
    # Enforce physical ordering with a minimum gap (rejection would bias the prior).
    fc = np.maximum(fc, wp + 0.04)
    sat = np.clip(np.maximum(sat, fc + 0.05), None, 0.75)
    tau = np.clip(soil.drainage_tau * np.exp(rng.normal(0, rel, n)), 0.05, 1.0)
    cn = np.clip(soil.curve_number + rng.normal(0, 3.0, n), 40, 95)
    et_mult = np.exp(rng.normal(0, u.et_multiplier_std, n))
    init = np.clip(rng.normal(u.initial_fraction_mean, u.initial_fraction_std, n), 0.05, 1.0)
    return {"theta_wp": wp, "theta_fc": fc, "theta_sat": sat, "tau": tau, "cn": cn, "et_mult": et_mult, "init_frac": init}


@dataclass(frozen=True)
class FarmDay:
    """Consequences of one day on the hidden farm (truth; evaluation & reward use only)."""

    ks: float
    actual_et_mm: float
    crop_et_mm: float
    runoff_mm: float
    drainage_mm: float
    storage_mm: float
    theta: float
    depletion_mm: float
    taw_mm: float
    root_depth_m: float
    residual_mm: float


class ReferenceFarm:
    def __init__(self, scenario: ScenarioConfig, rng: np.random.Generator):
        self._scenario = scenario
        self._calendar = wb.CropCalendar(scenario.crop)
        self._rng = rng
        params = draw_soil_parameters(scenario, rng)
        self._p = {k: float(v[0]) for k, v in params.items()}
        z0 = self._calendar.root_depth(0)
        p = self._p
        self._storage = (p["theta_wp"] + p["init_frac"] * (p["theta_fc"] - p["theta_wp"])) * z0 * 1000
        self._zr = z0
        self._day = 0
        n_stages = len(scenario.crop.stage_lengths_days)
        self._eta_stage = np.zeros(n_stages)
        self._etc_stage = np.zeros(n_stages)
        self._theta_history: list[float] = [self._storage / (z0 * 1000)]
        self._records: list[dict] = []

    # -- operational boundary -------------------------------------------------
    def step(self, irrigation_mm: float, rain_mm: float, eto_mm: float) -> FarmDay:
        """Apply an already-approved irrigation depth with realized weather."""
        if irrigation_mm < 0 or not np.isfinite(irrigation_mm):
            raise ValueError("Irrigation must be finite and nonnegative")
        day = self._day
        cal, p = self._calendar, self._p
        zr_next = cal.root_depth(day + 1)
        noise = float(np.exp(self._rng.normal(0, self._scenario.uncertainty.process_noise_rel_std)))
        flux = wb.step(self._storage, p["theta_wp"], p["theta_fc"], p["theta_sat"], p["tau"], p["cn"], self._zr, zr_next,
                       rain_mm, irrigation_mm, eto_mm, cal.kc(day), self._scenario.crop.depletion_p, p["init_frac"],
                       et_multiplier=p["et_mult"] * noise)
        stage = cal.stage(day)
        self._eta_stage[stage] += float(flux.actual_et_mm)
        self._etc_stage[stage] += float(flux.crop_et_mm)
        self._storage = float(flux.storage_mm)
        self._zr = zr_next
        self._day += 1
        theta = self._storage / (zr_next * 1000)
        self._theta_history.append(theta)
        result = FarmDay(float(flux.ks), float(flux.actual_et_mm), float(flux.crop_et_mm), float(flux.runoff_mm), float(flux.drainage_mm),
                         self._storage, theta, float(flux.depletion_mm), float(flux.taw_mm), zr_next, float(flux.residual_mm))
        self._records.append({"day": day, **result.__dict__})
        return result

    def yield_ratio(self) -> float:
        return wb.yield_proxy_ratio(self._eta_stage, self._etc_stage, self._scenario.crop.ky_stage)

    # -- sensor-only access ----------------------------------------------------
    def _sensor_theta(self, days_ago: int = 0) -> float:
        index = max(0, len(self._theta_history) - 1 - days_ago)
        return self._theta_history[index]

    # -- post-run evaluation only ----------------------------------------------
    def evaluation_record(self) -> dict:
        return {"hidden_parameters": dict(self._p), "daily": list(self._records), "yield_ratio": self.yield_ratio(),
                "eta_by_stage_mm": self._eta_stage.tolist(), "etc_by_stage_mm": self._etc_stage.tolist(),
                "label": "SIMULATED REFERENCE (hidden ground truth) — evaluation only"}
