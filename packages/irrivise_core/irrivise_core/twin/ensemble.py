"""Estimated Digital Twin: an ensemble belief over root-zone soil water.

Each of K members carries its own plausible soil parameters (drawn from the
same prior the hidden farm was drawn from — the twin knows the prior, never
the realization), its own initial wetness, and its own storage. Members are
propagated with OBSERVED past weather (which includes gauge/gridded error)
and the applied irrigation, plus multiplicative process noise, so
uncertainty grows when no measurement is taken.

Correction (CARAT step 6) is a 1-D Kalman update applied to the ensemble in
root-zone storage units (mm), implemented as a deterministic square-root
ensemble shift so that the ensemble mean and variance equal exactly

    K = P / (P + R),   mean' = mean + K (z - mean),   P' = (1 - K) P.

Degenerate cases: P below 1e-12 mm² is treated as 0; P + R == 0 → K = 0 (no update); members are clipped to
their physical bounds afterwards and the clip count is reported.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config.schemas import ScenarioConfig
from ..simulation import water_balance as wb
from ..simulation.reference_farm import draw_soil_parameters


VARIANCE_EPS_MM2 = 1e-12


@dataclass(frozen=True)
class MemberState:
    """Copy of ensemble arrays handed to CARAT / risk manager (no truth inside)."""

    storage_mm: np.ndarray
    theta_wp: np.ndarray
    theta_fc: np.ndarray
    theta_sat: np.ndarray
    tau: np.ndarray
    cn: np.ndarray
    et_mult: np.ndarray
    subsoil_frac: np.ndarray
    weights: np.ndarray
    root_depth_m: float
    day: int


@dataclass(frozen=True)
class BeliefSummary:
    day: int
    mean_storage_mm: float
    std_storage_mm: float
    q10_storage_mm: float
    q90_storage_mm: float
    mean_theta: float
    std_theta: float
    depletion_mm: float
    taw_mm: float
    raw_mm: float
    depletion_fraction: float
    ks_estimate: float
    root_depth_m: float
    days_since_observation: int
    effective_sample_size: float

    def as_dict(self) -> dict:
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


class EnsembleTwin:
    def __init__(self, scenario: ScenarioConfig, rng: np.random.Generator):
        self.scenario = scenario
        self.calendar = wb.CropCalendar(scenario.crop)
        self._rng = rng
        k = scenario.uncertainty.ensemble_size
        params = draw_soil_parameters(scenario, rng, size=k)
        self.theta_wp, self.theta_fc, self.theta_sat = params["theta_wp"], params["theta_fc"], params["theta_sat"]
        self.tau, self.cn, self.et_mult, self.subsoil_frac = params["tau"], params["cn"], params["et_mult"], params["init_frac"]
        self.root_depth_m = self.calendar.root_depth(0)
        z = self.root_depth_m * 1000
        self.storage_mm = (self.theta_wp + self.subsoil_frac * (self.theta_fc - self.theta_wp)) * z
        self.weights = np.full(k, 1.0 / k)
        self.day = 0
        self.last_observation_day: int | None = None

    # -- propagation -------------------------------------------------------------
    def predict(self, irrigation_mm: float, observed_rain_mm: float, observed_eto_mm: float) -> None:
        """Propagate one day with observed (past) weather; uncertainty grows via process noise."""
        cal = self.calendar
        zr_next = cal.root_depth(self.day + 1)
        noise = np.exp(self._rng.normal(0.0, self.scenario.uncertainty.process_noise_rel_std, self.storage_mm.shape))
        flux = wb.step(self.storage_mm, self.theta_wp, self.theta_fc, self.theta_sat, self.tau, self.cn, self.root_depth_m, zr_next,
                       observed_rain_mm, irrigation_mm, observed_eto_mm, cal.kc(self.day), self.scenario.crop.depletion_p,
                       self.subsoil_frac, et_multiplier=self.et_mult * noise)
        self.storage_mm = flux.storage_mm
        self.root_depth_m = zr_next
        self.day += 1

    # -- correction ------------------------------------------------------------
    def correct(self, theta_measured: float, sensor_std_m3m3: float, inflation: float = 1.0, gate_sigma: float | None = None) -> dict:
        """Kalman-style ensemble correction with an innovation (outlier) gate."""
        if not np.isfinite(theta_measured) or sensor_std_m3m3 < 0 or inflation < 1:
            raise ValueError("Invalid measurement or sensor variance")
        z_mm = theta_measured * self.root_depth_m * 1000
        r = (sensor_std_m3m3 * self.root_depth_m * 1000) ** 2 * inflation
        w = self.weights
        mean = float(np.sum(w * self.storage_mm))
        p = float(np.sum(w * (self.storage_mm - mean) ** 2))
        if p < VARIANCE_EPS_MM2:  # collapsed ensemble: treat float residue as exactly zero
            p = 0.0
        innovation = z_mm - mean
        diag = {"prior_mean_mm": mean, "prior_var_mm2": p, "measurement_mm": z_mm, "sensor_var_mm2": r, "innovation_mm": innovation}
        if gate_sigma is not None and (p + r) > 0 and abs(innovation) > gate_sigma * np.sqrt(p + r):
            diag.update({"applied": False, "reason": f"innovation exceeds {gate_sigma:g}σ outlier gate", "gain": 0.0,
                         "posterior_mean_mm": mean, "posterior_var_mm2": p, "clipped_members": 0})
            return diag
        denominator = p + r
        gain = p / denominator if denominator > 0 else 0.0
        new_mean = mean + gain * innovation
        shrink = np.sqrt(max(0.0, 1.0 - gain))
        updated = new_mean + shrink * (self.storage_mm - mean)
        z = self.root_depth_m * 1000
        low, high = self.theta_wp * z, self.theta_sat * z
        clipped = int(np.sum((updated < low) | (updated > high)))
        self.storage_mm = np.clip(updated, low, high)
        self.last_observation_day = self.day
        post_mean = float(np.sum(w * self.storage_mm))
        post_var = float(np.sum(w * (self.storage_mm - post_mean) ** 2))
        diag.update({"applied": True, "reason": "kalman ensemble update", "gain": gain, "posterior_mean_mm": post_mean,
                     "posterior_var_mm2": post_var, "analytic_posterior_var_mm2": (1 - gain) * p, "clipped_members": clipped})
        return diag

    # -- read-only views ---------------------------------------------------------
    def members(self) -> MemberState:
        return MemberState(self.storage_mm.copy(), self.theta_wp.copy(), self.theta_fc.copy(), self.theta_sat.copy(), self.tau.copy(),
                           self.cn.copy(), self.et_mult.copy(), self.subsoil_frac.copy(), self.weights.copy(), self.root_depth_m, self.day)

    def summary(self) -> BeliefSummary:
        w = self.weights
        z = self.root_depth_m * 1000
        s = self.storage_mm
        mean = float(np.sum(w * s))
        std = float(np.sqrt(max(0.0, np.sum(w * (s - mean) ** 2))))
        theta = s / z
        mean_theta = float(np.sum(w * theta))
        std_theta = float(np.sqrt(max(0.0, np.sum(w * (theta - mean_theta) ** 2))))
        taw = (self.theta_fc - self.theta_wp) * z
        depletion = np.maximum(0.0, self.theta_fc * z - s)
        p = self.scenario.crop.depletion_p
        ks = np.clip((taw - depletion) / ((1 - p) * taw), 0, 1)
        order = np.argsort(s)
        cdf = np.cumsum(w[order])
        q10 = float(s[order][np.searchsorted(cdf, 0.1)])
        q90 = float(s[order][min(len(s) - 1, np.searchsorted(cdf, 0.9))])
        since = self.day - self.last_observation_day if self.last_observation_day is not None else self.day + 1
        return BeliefSummary(self.day, mean, std, q10, q90, mean_theta, std_theta, float(np.sum(w * depletion)), float(np.sum(w * taw)),
                             float(np.sum(w * p * taw)), float(np.sum(w * depletion / taw)), float(np.sum(w * ks)), self.root_depth_m,
                             int(since), float(1.0 / np.sum(w ** 2)))
