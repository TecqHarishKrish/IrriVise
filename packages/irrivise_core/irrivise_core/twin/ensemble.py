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

Sensor-bias handling (``scenario.twin_bias``, METHODOLOGY.md §2.4):

* ``augmented`` — each member i also carries a candidate sensor offset b_i
  (m³/m³). The predicted reading is y_i = s_i + b_i·Z (Z = root depth in mm).
  The update is the scalar-observation ensemble square-root filter
  (Whitaker & Hamill 2002) on the joint state (s, b):

      K_s = C_sy / (P_yy + R),  K_b = C_by / (P_yy + R),
      x̄' = x̄ + K (z − ȳ),      x_i' − x̄' = (x_i − x̄) − α K (y_i − ȳ),
      α = 1 / (1 + √(R / (P_yy + R))).

  With every b_i = 0 this is exactly the update above (1 − αK = √(1 − K)).
  Offsets start at deterministic N(0, σ_b²) quantiles (no draws from the twin's
  random stream, so the soil ensemble is identical in every mode) and their
  spread is inflated by a small daily random walk so a drifting or stuck
  sensor can still be followed.
* ``innovation_monitor`` — a two-sided CUSUM on normalised innovations
  ν = (z − ȳ)/√(P + R). While one side is above its alarm level, readings
  that disagree in that direction get R multiplied by ``monitor_downweight``.
* ``none`` — the original unbiased-sensor update.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

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
        self.bias_cfg = scenario.twin_bias
        self.bias_m3m3 = np.zeros(k)
        if self.bias_cfg.method == "augmented" and self.bias_cfg.prior_std_m3m3 > 0:
            q = np.array([NormalDist().inv_cdf((i + 0.5) / k) for i in range(k)])
            self.bias_m3m3 = self.bias_cfg.prior_std_m3m3 * (q - q.mean()) / q.std()
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0

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
        if self.bias_cfg.method == "augmented":
            self._decouple_and_drift_offsets()

    def _decouple_and_drift_offsets(self) -> None:
        """Drop the storage–offset cross-covariance, keep the offset variance, then add random-walk drift.

        An update leaves storage and offset anti-correlated. The soil dynamics then
        contract the storage spread (drainage to field capacity, ET near wilting
        point) while the offsets keep theirs, so the stale anti-correlation can flip
        the sign of the storage gain at the next reading. Each forecast step
        therefore projects the offset perturbations orthogonal to the storage
        perturbations and rescales them to their previous variance (a decoupled,
        two-stage bias filter). Everything is deterministic: no random draws.
        """
        w = self.weights
        b_mean = float(np.sum(w * self.bias_m3m3))
        db = self.bias_m3m3 - b_mean
        var_b = float(np.sum(w * db ** 2))
        ds = self.storage_mm - float(np.sum(w * self.storage_mm))
        var_s = float(np.sum(w * ds ** 2))
        if var_b > 0 and var_s > VARIANCE_EPS_MM2:
            projected = db - (float(np.sum(w * db * ds)) / var_s) * ds
            var_p = float(np.sum(w * projected ** 2))
            if var_p > 0:
                db = projected * np.sqrt(var_b / var_p)
        drift = self.bias_cfg.drift_std_m3m3
        if var_b > 0 and drift > 0:
            db = db * np.sqrt(1.0 + drift ** 2 / var_b)
        self.bias_m3m3 = b_mean + db

    # -- correction ------------------------------------------------------------
    def correct(self, theta_measured: float, sensor_std_m3m3: float, inflation: float = 1.0, gate_sigma: float | None = None) -> dict:
        """Kalman-style ensemble correction with an innovation (outlier) gate and sensor-bias handling."""
        if not np.isfinite(theta_measured) or sensor_std_m3m3 < 0 or inflation < 1:
            raise ValueError("Invalid measurement or sensor variance")
        zscale = self.root_depth_m * 1000
        z_mm = theta_measured * zscale
        r = (sensor_std_m3m3 * zscale) ** 2 * inflation
        w = self.weights
        method = self.bias_cfg.method
        mean = float(np.sum(w * self.storage_mm))
        p = float(np.sum(w * (self.storage_mm - mean) ** 2))
        if p < VARIANCE_EPS_MM2:  # collapsed ensemble: treat float residue as exactly zero
            p = 0.0
        b_mean = float(np.sum(w * self.bias_m3m3))
        y = self.storage_mm + self.bias_m3m3 * zscale            # predicted reading per member (mm)
        y_mean = float(np.sum(w * y))
        p_yy = float(np.sum(w * (y - y_mean) ** 2))
        if p_yy < VARIANCE_EPS_MM2:
            p_yy = 0.0
        innovation = z_mm - y_mean
        diag = {"prior_mean_mm": mean, "prior_var_mm2": p, "measurement_mm": z_mm, "sensor_var_mm2": r, "innovation_mm": innovation,
                "bias_method": method, "prior_bias_m3m3": b_mean}
        nu = innovation / np.sqrt(p_yy + r) if (p_yy + r) > 0 else 0.0
        diag["normalized_innovation"] = float(nu)
        if gate_sigma is not None and (p_yy + r) > 0 and abs(nu) > gate_sigma:
            diag.update({"applied": False, "reason": f"innovation exceeds {gate_sigma:g}σ outlier gate", "gain": 0.0,
                         "posterior_mean_mm": mean, "posterior_var_mm2": p, "clipped_members": 0, "posterior_bias_m3m3": b_mean})
            return diag
        if method == "innovation_monitor":
            k_slack, h = self.bias_cfg.monitor_k, self.bias_cfg.monitor_h
            flagged_pos, flagged_neg = self.cusum_pos > h, self.cusum_neg > h  # alarm state before this reading
            self.cusum_pos = max(0.0, self.cusum_pos + nu - k_slack)
            self.cusum_neg = max(0.0, self.cusum_neg - nu - k_slack)
            if (flagged_pos and innovation > 0) or (flagged_neg and innovation < 0):
                r *= self.bias_cfg.monitor_downweight
                diag["downweighted"] = True
            diag.update({"cusum_pos": self.cusum_pos, "cusum_neg": self.cusum_neg,
                         "bias_suspected": bool(self.cusum_pos > h or self.cusum_neg > h)})
        denominator = p_yy + r
        if method != "augmented":  # y == storage, so C_sy == P: keep the original arithmetic exactly
            c_sy, gain_b, alpha = p, 0.0, 0.0
            gain = p / denominator if denominator > 0 else 0.0
        elif denominator > 0:
            c_sy = float(np.sum(w * (self.storage_mm - mean) * (y - y_mean)))
            c_by = float(np.sum(w * (self.bias_m3m3 - b_mean) * (y - y_mean)))
            gain, gain_b = c_sy / denominator, c_by / denominator
            alpha = 1.0 / (1.0 + np.sqrt(r / denominator))
        else:
            c_sy, gain, gain_b, alpha = 0.0, 0.0, 0.0, 0.0
        new_mean = mean + gain * innovation
        if method == "augmented":
            updated = new_mean + (self.storage_mm - mean) - alpha * gain * (y - y_mean)
            self.bias_m3m3 = (b_mean + gain_b * innovation) + (self.bias_m3m3 - b_mean) - alpha * gain_b * (y - y_mean)
        else:  # identical arithmetic to the original update (bias members are all zero)
            updated = new_mean + np.sqrt(max(0.0, 1.0 - gain)) * (self.storage_mm - mean)
        low, high = self.theta_wp * zscale, self.theta_sat * zscale
        clipped = int(np.sum((updated < low) | (updated > high)))
        self.storage_mm = np.clip(updated, low, high)
        self.last_observation_day = self.day
        post_mean = float(np.sum(w * self.storage_mm))
        post_var = float(np.sum(w * (self.storage_mm - post_mean) ** 2))
        diag.update({"applied": True, "reason": "kalman ensemble update" if method != "augmented" else "joint soil + sensor-offset update",
                     "gain": gain, "posterior_mean_mm": post_mean, "posterior_var_mm2": post_var,
                     "analytic_posterior_var_mm2": (1 - gain) * p if method != "augmented" else p - gain * c_sy, "clipped_members": clipped,
                     "posterior_bias_m3m3": float(np.sum(w * self.bias_m3m3))})
        return diag

    def bias_state(self) -> dict:
        """Current belief about the sensor offset (for diagnostics and the UI)."""
        w = self.weights
        b_mean = float(np.sum(w * self.bias_m3m3))
        out = {"method": self.bias_cfg.method, "mean_m3m3": b_mean,
               "std_m3m3": float(np.sqrt(max(0.0, np.sum(w * (self.bias_m3m3 - b_mean) ** 2))))}
        if self.bias_cfg.method == "innovation_monitor":
            out.update({"cusum_pos": self.cusum_pos, "cusum_neg": self.cusum_neg,
                        "bias_suspected": bool(max(self.cusum_pos, self.cusum_neg) > self.bias_cfg.monitor_h)})
        return out

    def effective_sensor_std(self, sensor_std_m3m3: float) -> float:
        """Sensor std seen by the soil state once offset uncertainty is included (used by VOI)."""
        w = self.weights
        b_mean = float(np.sum(w * self.bias_m3m3))
        var_b = float(np.sum(w * (self.bias_m3m3 - b_mean) ** 2))
        return float(sensor_std_m3m3) if var_b <= 0 else float(np.sqrt(sensor_std_m3m3 ** 2 + var_b))

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
