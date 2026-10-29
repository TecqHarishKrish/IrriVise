"""Daily single-layer root-zone water balance (FAO-56 style), vectorised.

All water quantities are depths in mm over the current root zone. For a
root-zone storage S (mm) on day t:

    S' = S + E_root + P + I - RO - ETa - DP

where E_root is water added to the control volume when roots deepen into
subsoil, P rainfall, I irrigation, RO surface runoff (SCS curve number plus
saturation excess), ETa actual crop evapotranspiration and DP deep drainage.
Every component is computed explicitly; nothing is silently clamped, and the
residual of the identity above is returned so callers can reject any day whose
mass balance is violated beyond ``MASS_TOLERANCE_MM``.

Water-stress coefficient (FAO-56 eq. 84):  Ks = (TAW - Dr) / ((1 - p) TAW)
clipped to [0, 1], with Dr the root-zone depletion below field capacity.
ETa = Ks · Kc · ET0 (single crop coefficient approach).

This is a CPU-cheap surrogate for RL training and CARAT lookahead. It is NOT
calibrated against AquaCrop or field data; see METHODOLOGY.md.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config.schemas import CropProfile

MASS_TOLERANCE_MM = 1e-6


class MassBalanceError(ArithmeticError):
    pass


@dataclass(frozen=True)
class CropCalendar:
    """Day-indexed crop coefficients, root depth and stage sensitivity."""

    crop: CropProfile

    def stage(self, day: int) -> int:
        bounds = np.cumsum(self.crop.stage_lengths_days)
        return int(min(3, np.searchsorted(bounds, day, side="right")))

    def kc(self, day: int) -> float:
        """FAO-56 piecewise-linear Kc curve (Fig. 34)."""
        ini, dev, mid, late = self.crop.stage_lengths_days
        c = self.crop
        if day < ini:
            return c.kc_ini
        if day < ini + dev:
            return c.kc_ini + (c.kc_mid - c.kc_ini) * (day - ini) / dev
        if day < ini + dev + mid:
            return c.kc_mid
        frac = min(1.0, (day - ini - dev - mid) / late)
        return c.kc_mid + (c.kc_end - c.kc_mid) * frac

    def root_depth(self, day: int) -> float:
        """Linear root growth from root_min to root_max over the initial+development stages."""
        ini, dev, _, _ = self.crop.stage_lengths_days
        frac = min(1.0, max(0.0, day / (ini + dev)))
        return self.crop.root_min_m + (self.crop.root_max_m - self.crop.root_min_m) * frac

    def ky(self, day: int) -> float:
        return self.crop.ky_stage[self.stage(day)]

    @property
    def length(self) -> int:
        return self.crop.season_length


def scs_runoff(rain_mm: np.ndarray | float, curve_number: np.ndarray | float) -> np.ndarray:
    """USDA SCS curve-number runoff (mm), Ia = 0.2 S."""
    rain = np.asarray(rain_mm, dtype=float)
    s = 25400.0 / np.asarray(curve_number, dtype=float) - 254.0
    ia = 0.2 * s
    excess = np.maximum(0.0, rain - ia)
    return np.where(rain > ia, excess ** 2 / (excess + s), 0.0)


@dataclass
class DayFlux:
    """Arrays of daily fluxes (mm unless stated). Shapes broadcast over members/actions."""

    storage_mm: np.ndarray
    root_expansion_mm: np.ndarray
    runoff_mm: np.ndarray
    actual_et_mm: np.ndarray
    crop_et_mm: np.ndarray
    drainage_mm: np.ndarray
    ks: np.ndarray
    depletion_mm: np.ndarray
    taw_mm: np.ndarray
    residual_mm: np.ndarray


def step(storage_mm, theta_wp, theta_fc, theta_sat, tau, curve_number, zr_prev: float, zr_next: float,
         rain_mm, irrigation_mm, eto_mm, kc: float, p: float, subsoil_fraction, et_multiplier=1.0,
         check: bool = True) -> DayFlux:
    """Advance one day. All array-like inputs broadcast (members × actions).

    ``subsoil_fraction`` is the relative wetness (0 = WP, 1 = FC) of soil newly
    reached by deepening roots.
    """
    s0 = np.asarray(storage_mm, dtype=float)
    wp, fc, sat = (np.asarray(x, dtype=float) for x in (theta_wp, theta_fc, theta_sat))
    rain = np.asarray(rain_mm, dtype=float)
    irr = np.asarray(irrigation_mm, dtype=float)
    eto = np.asarray(eto_mm, dtype=float)
    if check:
        if np.any(rain < 0) or np.any(irr < 0) or np.any(eto < 0):
            raise ValueError("Rainfall, irrigation and ET0 must be nonnegative")
        if not (np.all(np.isfinite(s0)) and np.all(np.isfinite(rain)) and np.all(np.isfinite(irr)) and np.all(np.isfinite(eto))):
            raise ValueError("Water-balance inputs must be finite")
        if zr_next < zr_prev:
            raise ValueError("Root depth cannot decrease in this model")
    dz_mm = (zr_next - zr_prev) * 1000.0
    subsoil_theta = wp + np.clip(subsoil_fraction, 0.0, 1.0) * (fc - wp)
    expansion = dz_mm * subsoil_theta * np.ones_like(s0)
    s = s0 + expansion
    z_mm = zr_next * 1000.0
    s_wp, s_fc, s_sat = wp * z_mm, fc * z_mm, sat * z_mm
    runoff_cn = scs_runoff(rain, curve_number)
    s = s + rain - runoff_cn + irr
    sat_excess = np.maximum(0.0, s - s_sat)
    s = s - sat_excess
    runoff = runoff_cn + sat_excess
    taw = s_fc - s_wp
    depletion = np.maximum(0.0, s_fc - s)
    ks = np.clip((taw - depletion) / ((1.0 - p) * taw), 0.0, 1.0)
    etc = kc * eto * np.asarray(et_multiplier, dtype=float)
    eta = np.minimum(ks * etc, np.maximum(0.0, s - s_wp))
    s = s - eta
    drainage = tau * np.maximum(0.0, s - s_fc)
    s = s - drainage
    residual = s0 + expansion + rain + irr - runoff - eta - drainage - s
    if check and np.max(np.abs(residual)) > MASS_TOLERANCE_MM:
        raise MassBalanceError(f"Root-zone mass balance residual {np.max(np.abs(residual)):.3e} mm exceeds tolerance")
    return DayFlux(
        storage_mm=s, root_expansion_mm=np.broadcast_to(expansion, s.shape).copy(), runoff_mm=np.broadcast_to(runoff, s.shape).copy(),
        actual_et_mm=eta, crop_et_mm=np.broadcast_to(etc, s.shape).copy(), drainage_mm=drainage, ks=ks,
        depletion_mm=np.maximum(0.0, s_fc - s), taw_mm=np.broadcast_to(taw, s.shape).copy(), residual_mm=residual,
    )


def yield_proxy_ratio(eta_by_stage: np.ndarray, etc_by_stage: np.ndarray, ky_stage: tuple[float, ...]) -> float:
    """FAO-33 multiplicative stage yield response: Ya/Ym = Π_s [1 - Ky_s (1 - ETa_s/ETc_s)], clipped to [0, 1].

    This is a PROXY used for the terminal RL reward and fast comparisons, not
    an AquaCrop or measured yield.
    """
    ratio = 1.0
    for eta, etc, ky in zip(eta_by_stage, etc_by_stage, ky_stage):
        if etc > 1e-9:
            ratio *= max(0.0, 1.0 - ky * (1.0 - min(1.0, eta / etc)))
    return float(min(1.0, max(0.0, ratio)))
