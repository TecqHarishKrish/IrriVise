"""One simulated season: hidden farm + estimated twin + gateway + budgets.

Daily execution order (identical for RL training and evaluation):

1. ``view()``          — forecast from past observations; twin summary; budgets.
2. ``observe()``       — optional, budgeted, noisy reading → twin correction.
3. ``apply(mm)``       — approved irrigation reaches the hidden farm, which
                         advances with REALIZED weather; the realized weather is
                         then revealed to the agent (with gauge error) and the
                         twin propagates with it. Day index increments.

Nothing returned by ``view()`` depends on the hidden farm state or on weather
of the current or future days.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config.schemas import ScenarioConfig
from ..data.weather import Season
from ..twin.ensemble import BeliefSummary, EnsembleTwin, MemberState
from ..util.repro import rng as make_rng
from .forecast import ClimatologyForecaster, Forecast
from .reference_farm import FarmDay, ReferenceFarm
from .sensor import Measurement, SensorGateway
from . import water_balance as wb


@dataclass(frozen=True)
class AgentView:
    """Everything a policy / CARAT may legitimately know on a decision day."""

    day: int
    date: str
    season_length: int
    stage: int
    kc: float
    ky: float
    belief: BeliefSummary
    forecast: Forecast
    observed_rain_mm: tuple[float, ...]
    observed_eto_mm: tuple[float, ...]
    remaining_water_mm: float
    seasonal_budget_mm: float
    daily_max_mm: float
    remaining_observations: int
    observation_budget: int


class FieldWorld:
    def __init__(self, scenario: ScenarioConfig, season: Season, forecaster: ClimatologyForecaster, world_seed: int,
                 horizon: int | None = None):
        length = scenario.crop.season_length
        if len(season) < length:
            raise ValueError(f"Season {season.season_id} has {len(season)} days; crop needs {length}")
        self.scenario = scenario
        self.season = season
        self.forecaster = forecaster
        self.calendar = wb.CropCalendar(scenario.crop)
        self.horizon = horizon or scenario.carat.horizon_days
        key = (world_seed, season.season_id)
        # Independent random streams (common random numbers across methods).
        self._farm = ReferenceFarm(scenario, make_rng(*key, "farm"))
        self.twin = EnsembleTwin(scenario, make_rng(*key, "twin"))
        self.sensor = SensorGateway(self._farm, scenario.sensor, scenario.observation_budget, make_rng(*key, "sensor"))
        self._gauge_rng = make_rng(*key, "gauge")
        self.day = 0
        self.water_used_mm = 0.0
        self.observed_rain: list[float] = []
        self.observed_eto: list[float] = []

    @property
    def length(self) -> int:
        return self.scenario.crop.season_length

    @property
    def done(self) -> bool:
        return self.day >= self.length

    @property
    def remaining_water_mm(self) -> float:
        return max(0.0, self.scenario.seasonal_budget_mm - self.water_used_mm)

    def forecast(self) -> Forecast:
        return self.forecaster.forecast(self.day, self.observed_rain, self.observed_eto, self.horizon)

    def view(self, forecast: Forecast | None = None) -> AgentView:
        if self.done:
            raise RuntimeError("Season finished: no further decisions")
        d = self.day
        return AgentView(d, self.season.dates[d], self.length, self.calendar.stage(d), self.calendar.kc(d), self.calendar.ky(d),
                         self.twin.summary(), forecast or self.forecast(), tuple(self.observed_rain), tuple(self.observed_eto),
                         self.remaining_water_mm, self.scenario.seasonal_budget_mm, self.scenario.daily_max_mm,
                         self.sensor.remaining, self.scenario.observation_budget)

    def members(self) -> MemberState:
        return self.twin.members()

    def observe(self, correct: bool = True) -> tuple[Measurement, dict | None]:
        """Request one reading; optionally correct the twin. Returns (measurement, correction diagnostics)."""
        measurement = self.sensor.measure(self.day)
        if measurement.status != "ok" or not correct:
            return measurement, None
        cfg = self.scenario.sensor
        inflation = 1.0
        if measurement.state_day is not None and measurement.state_day < self.day:
            inflation = 1.0 + (self.day - measurement.state_day)  # stale reading → larger effective variance
        diag = self.twin.correct(measurement.theta_m3m3, max(cfg.noise_std_m3m3, 1e-4), inflation=inflation,
                                 gate_sigma=cfg.outlier_sigma)
        return measurement, diag

    def apply(self, applied_mm: float) -> FarmDay:
        if self.done:
            raise RuntimeError("Season finished: no action after termination")
        if applied_mm < -1e-12 or applied_mm > self.scenario.daily_max_mm + 1e-9 or applied_mm > self.remaining_water_mm + 1e-9:
            raise ValueError("Applied irrigation violates a hard constraint (risk manager bypassed?)")
        applied_mm = max(0.0, applied_mm)
        d = self.day
        rain, eto = float(self.season.rain_mm[d]), float(self.season.eto_mm[d])
        result = self._farm.step(applied_mm, rain, eto)
        self.water_used_mm += applied_mm
        # The day's weather becomes known only now, with gauge/gridded error.
        rel = self.scenario.uncertainty.observed_rain_rel_std
        observed_rain = rain * float(np.exp(self._gauge_rng.normal(0, rel) - rel ** 2 / 2)) if rain > 0 else 0.0
        self.observed_rain.append(observed_rain)
        self.observed_eto.append(eto)
        self.twin.predict(applied_mm, observed_rain, eto)
        self.day += 1
        return result

    def yield_ratio(self) -> float:
        return self._farm.yield_ratio()

    def evaluation_record(self) -> dict:
        """POST-RUN ONLY: hidden truth for the evaluator."""
        if not self.done:
            raise PermissionError("Ground truth is available only after the season is complete")
        return self._farm.evaluation_record()
