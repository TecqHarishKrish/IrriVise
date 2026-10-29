"""Observation gateway: the only operational path from hidden truth to the twin.

A reading is produced only when requested, only while the observation budget
lasts, and the budget is charged exactly once per successful reading (failed
attempts are charged only when ``charge_failed_attempts`` is configured).
Every attempt is recorded.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from ..config.schemas import SensorConfig
from .reference_farm import ReferenceFarm


@dataclass(frozen=True)
class Measurement:
    day: int
    status: str                    # ok | missing | budget_exhausted | implausible
    theta_m3m3: float | None
    noise_std_m3m3: float
    state_day: int | None          # day of the soil state the reading reflects (delayed sensors)
    charged: bool
    flags: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["flags"] = list(self.flags)
        return data


class SensorGateway:
    def __init__(self, farm: ReferenceFarm, config: SensorConfig, budget: int, rng: np.random.Generator):
        if budget < 0:
            raise ValueError("Observation budget must be nonnegative")
        self._farm = farm
        self.config = config
        self.budget = budget
        self.used = 0
        self.attempts = 0
        self._rng = rng
        self._stuck_value: float | None = None
        self.events: list[dict] = []

    @property
    def remaining(self) -> int:
        return self.budget - self.used

    def is_available(self, day: int) -> bool:
        return self.remaining > 0

    def measure(self, day: int) -> Measurement:
        cfg = self.config
        if self.remaining <= 0:
            result = Measurement(day, "budget_exhausted", None, cfg.noise_std_m3m3, None, False, ("no_budget",))
            self.events.append(result.as_dict())
            return result
        self.attempts += 1
        flags: list[str] = []
        noise = float(self._rng.normal(0.0, cfg.noise_std_m3m3)) if cfg.noise_std_m3m3 > 0 else 0.0
        missing_draw = float(self._rng.random())
        if cfg.mode == "missing" and missing_draw < cfg.missing_probability:
            charged = cfg.charge_failed_attempts
            if charged:
                self.used += 1
            result = Measurement(day, "missing", None, cfg.noise_std_m3m3, None, charged, ("dropout",))
            self.events.append(result.as_dict())
            return result
        state_day = day
        if cfg.mode == "delayed":
            state_day = max(0, day - cfg.delay_days)
            value = self._farm._sensor_theta(days_ago=day - state_day) + noise
            flags.append("stale")
        elif cfg.mode == "stuck" and day >= cfg.stuck_after_day:
            if self._stuck_value is None:
                self._stuck_value = self._farm._sensor_theta() + noise
            value = self._stuck_value
            flags.append("stuck_sensor_simulated")
        else:
            value = self._farm._sensor_theta() + noise
            if cfg.mode == "biased":
                value += cfg.bias_m3m3
                flags.append("bias_simulated")
        self.used += 1
        if not np.isfinite(value) or not 0.0 <= value <= 0.8:
            result = Measurement(day, "implausible", float(value) if np.isfinite(value) else None, cfg.noise_std_m3m3, state_day, True, tuple(flags + ["rejected_implausible"]))
        else:
            result = Measurement(day, "ok", float(value), cfg.noise_std_m3m3, state_day, True, tuple(flags))
        self.events.append(result.as_dict())
        return result
