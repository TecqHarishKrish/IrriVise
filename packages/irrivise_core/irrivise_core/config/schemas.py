"""Typed, hashable configuration objects for the IrriVise scientific engine.

Every experiment, simulation and training job is described by these models so
that its configuration can be serialised, hashed and stored in a manifest.
Canonical units: millimetres (water depths), days, m³/m³ (volumetric water
content), metres (root depth), t/ha (yield).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ACTIONS_MM: tuple[float, ...] = (0.0, 5.0, 10.0, 15.0, 20.0)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SoilProfile(_Frozen):
    """Single-layer root-zone soil hydraulic description."""

    name: str
    theta_wp: float = Field(gt=0, lt=0.6, description="Permanent wilting point, m³/m³")
    theta_fc: float = Field(gt=0, lt=0.7, description="Field capacity, m³/m³")
    theta_sat: float = Field(gt=0, le=0.8, description="Saturation, m³/m³")
    drainage_tau: float = Field(gt=0, le=1, description="Fraction of water above FC drained per day")
    curve_number: float = Field(ge=30, le=98, description="SCS curve number for surface runoff")
    source: str = ""

    @model_validator(mode="after")
    def _ordered(self) -> "SoilProfile":
        if not self.theta_wp < self.theta_fc < self.theta_sat:
            raise ValueError("Soil water bounds must satisfy wilting point < field capacity < saturation")
        return self


class CropProfile(_Frozen):
    """FAO-56 style crop calendar with FAO-33 stage yield-response factors."""

    name: str
    stage_lengths_days: tuple[int, int, int, int] = Field(description="initial, development, mid, late")
    kc_ini: float = Field(gt=0, le=1.5)
    kc_mid: float = Field(gt=0, le=1.5)
    kc_end: float = Field(gt=0, le=1.5)
    root_min_m: float = Field(ge=0.1, le=3)
    root_max_m: float = Field(ge=0.1, le=3)
    depletion_p: float = Field(gt=0, lt=1, description="FAO-56 soil water depletion fraction for no stress")
    ky_stage: tuple[float, float, float, float] = Field(description="Yield response factor per stage")
    max_yield_t_ha: float = Field(gt=0, le=30, description="Potential yield used only by the yield proxy")
    source: str = ""

    @field_validator("stage_lengths_days")
    @classmethod
    def _positive_stages(cls, value: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        if any(v < 1 for v in value) or sum(value) > 250:
            raise ValueError("Stage lengths must be positive and total at most 250 days")
        return value

    @model_validator(mode="after")
    def _roots(self) -> "CropProfile":
        if self.root_min_m > self.root_max_m:
            raise ValueError("Minimum root depth must not exceed maximum root depth")
        if any(not 0 <= k <= 2.5 for k in self.ky_stage):
            raise ValueError("Ky values must be within [0, 2.5]")
        return self

    @property
    def season_length(self) -> int:
        return int(sum(self.stage_lengths_days))


class RewardWeights(_Frozen):
    """Decomposed reward weights (see METHODOLOGY.md §Reward)."""

    water: float = Field(default=0.2, ge=0, le=10)
    stress: float = Field(default=1.0, ge=0, le=10)
    violation: float = Field(default=2.0, ge=0, le=20)
    observation: float = Field(default=0.1, ge=0, le=10)
    terminal_yield: float = Field(default=5.0, ge=0, le=100)


class SensorConfig(_Frozen):
    """Simulated root-zone soil-moisture sensor."""

    noise_std_m3m3: float = Field(default=0.02, ge=0, le=0.2)
    mode: Literal["nominal", "missing", "biased", "stuck", "delayed"] = "nominal"
    missing_probability: float = Field(default=0.25, ge=0, le=1)
    bias_m3m3: float = Field(default=0.03, ge=-0.2, le=0.2)
    stuck_after_day: int = Field(default=40, ge=0, le=400)
    delay_days: int = Field(default=2, ge=0, le=30)
    outlier_sigma: float = Field(default=4.0, gt=0, le=50, description="Innovation gate in standard deviations")
    charge_failed_attempts: bool = False


class UncertaintyConfig(_Frozen):
    """Sources of uncertainty in the hidden farm and in the estimated twin."""

    ensemble_size: int = Field(default=20, ge=2, le=200)
    initial_fraction_mean: float = Field(default=0.7, ge=0, le=1, description="Initial storage as fraction of TAW above WP")
    initial_fraction_std: float = Field(default=0.12, ge=0, le=0.5)
    soil_param_rel_std: float = Field(default=0.08, ge=0, le=0.3)
    et_multiplier_std: float = Field(default=0.08, ge=0, le=0.5)
    process_noise_rel_std: float = Field(default=0.10, ge=0, le=0.5, description="Daily multiplicative ET noise")
    observed_rain_rel_std: float = Field(default=0.15, ge=0, le=1, description="Gauge/gridded rain error seen by the agent")


class TwinBiasConfig(_Frozen):
    """How the twin guards against a sensor with a persistent offset (METHODOLOGY.md §2.4).

    ``augmented``: every ensemble member also carries a candidate sensor offset
    (prior N(0, prior_std²), slow random-walk drift); each reading updates storage
    and offset jointly, so a persistent one-sided disagreement is gradually
    attributed to the sensor instead of the soil.
    ``innovation_monitor``: two-sided CUSUM on normalised innovations; while a
    persistent one-sided drift is flagged, readings on that side are down-weighted.
    ``none``: the original unbiased-sensor update.
    """

    method: Literal["none", "innovation_monitor", "augmented"] = "augmented"
    prior_std_m3m3: float = Field(default=0.015, ge=0, le=0.2, description="Prior std of the sensor offset (tuned on validation seasons)")
    drift_std_m3m3: float = Field(default=0.003, ge=0, le=0.05, description="Daily random-walk std of the offset (tuned on validation seasons)")
    monitor_k: float = Field(default=0.5, ge=0, le=5, description="CUSUM slack, in innovation standard deviations")
    monitor_h: float = Field(default=3.0, gt=0, le=50, description="CUSUM alarm level, in innovation standard deviations")
    monitor_downweight: float = Field(default=10.0, ge=1, le=1e6, description="Sensor-variance multiplier while flagged")


class CaratConfig(_Frozen):
    """CARAT decision layer: lookahead value model, regret and VOI."""

    horizon_days: int = Field(default=5, ge=1, le=14)
    discount: float = Field(default=0.97, gt=0, le=1)
    hypothetical_samples: int = Field(default=16, ge=1, le=256)
    observation_cost: float = Field(default=0.03, ge=0, le=10, description="Reward units per observation")
    budget_shadow_price: float = Field(default=0.02, ge=0, le=10, description="Base reward-unit price of a scarce observation")
    observe_threshold: float = Field(default=0.0, ge=-10, le=10)
    voi_update: Literal["reweight", "kalman"] = "reweight"
    regret_tolerance: float = Field(default=1e-9, ge=0, le=1e-3)
    terminal_depletion_weight: float = Field(default=0.5, ge=0, le=10)


class RiskConfig(_Frozen):
    """Soft, model-based crop-stress risk layer. Hard limits are always enforced."""

    enabled: bool = True
    max_stress_probability: float = Field(default=0.5, ge=0, le=1)
    sensitive_ky: float = Field(default=1.0, ge=0, le=3, description="Stages with Ky at or above this are stress-sensitive")
    max_waste_fraction: float = Field(default=0.6, ge=0, le=1)


class ScenarioConfig(_Frozen):
    """A field scenario: crop, soil, budgets and uncertainty for one season."""

    crop: CropProfile
    soil: SoilProfile
    planting_mmdd: str = "06-15"
    daily_max_mm: float = Field(default=20, ge=0, le=100)
    seasonal_budget_mm: float = Field(default=350, ge=0, le=3000)
    observation_budget: int = Field(default=10, ge=0, le=365)
    sensor: SensorConfig = SensorConfig()
    uncertainty: UncertaintyConfig = UncertaintyConfig()
    twin_bias: TwinBiasConfig = TwinBiasConfig()
    reward: RewardWeights = RewardWeights()
    carat: CaratConfig = CaratConfig()
    risk: RiskConfig = RiskConfig()
    actions_mm: tuple[float, ...] = ACTIONS_MM

    @field_validator("planting_mmdd")
    @classmethod
    def _mmdd(cls, value: str) -> str:
        from datetime import date

        try:
            date.fromisoformat(f"2001-{value}")
        except ValueError as exc:
            raise ValueError("planting_mmdd must be MM-DD (non-leap day)") from exc
        return value

    @field_validator("actions_mm")
    @classmethod
    def _actions(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if not value or any(a < 0 for a in value) or list(value) != sorted(set(value)):
            raise ValueError("actions_mm must be unique, ascending and nonnegative")
        return value


class PPOHyperparameters(_Frozen):
    learning_rate: float = Field(default=3e-4, ge=1e-6, le=1e-2)
    n_steps: int = Field(default=1024, ge=64, le=8192)
    batch_size: int = Field(default=64, ge=16, le=1024)
    n_epochs: int = Field(default=10, ge=1, le=50)
    gamma: float = Field(default=0.99, ge=0.8, le=0.9999)
    gae_lambda: float = Field(default=0.95, ge=0.5, le=1)
    clip_range: float = Field(default=0.2, gt=0, le=0.5)
    ent_coef: float = Field(default=0.01, ge=0, le=0.1)
    vf_coef: float = Field(default=0.5, ge=0, le=2)
    max_grad_norm: float = Field(default=0.5, gt=0, le=10)
    net_arch: tuple[int, ...] = (64, 64)

    @model_validator(mode="after")
    def _batch(self) -> "PPOHyperparameters":
        if self.batch_size > self.n_steps:
            raise ValueError("batch_size must not exceed n_steps")
        if not 1 <= len(self.net_arch) <= 4 or any(not 8 <= n <= 512 for n in self.net_arch):
            raise ValueError("net_arch must have 1–4 layers of 8–512 units")
        return self


class TrainingConfig(_Frozen):
    preset: Literal["cpu_quick", "cpu_standard", "cpu_research", "custom"] = "cpu_quick"
    total_timesteps: int = Field(default=5000, ge=256, le=3_000_000)
    seeds: tuple[int, ...] = (42,)
    eval_freq_steps: int = Field(default=2500, ge=256, le=200_000)
    early_stop_evals: int = Field(default=0, ge=0, le=100, description="0 disables early stopping")
    domain_randomization: bool = True
    hyperparameters: PPOHyperparameters = PPOHyperparameters()
    max_wall_seconds: int = Field(default=3600, ge=10, le=86_400)

    @field_validator("seeds")
    @classmethod
    def _seeds(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not 1 <= len(value) <= 10 or any(not 0 <= s < 2**31 for s in value) or len(set(value)) != len(value):
            raise ValueError("Provide 1–10 unique nonnegative seeds")
        return value
