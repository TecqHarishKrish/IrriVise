"""Deterministic, explicitly approximate water-balance and CARAT primitives.

The crop score here is a training proxy, never a measured or AquaCrop yield.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, sqrt
from random import Random


@dataclass(frozen=True)
class Soil:
    wilting: float = 0.10
    field_capacity: float = 0.27
    saturation: float = 0.42
    root_depth_m: float = 0.60

    def __post_init__(self) -> None:
        if not (0 <= self.wilting < self.field_capacity < self.saturation <= 0.8):
            raise ValueError("Soil water bounds must increase from wilting to saturation")
        if not 0.1 <= self.root_depth_m <= 3:
            raise ValueError("Root depth must be between 0.1 and 3 m")

    def mm(self, theta: float) -> float:
        return theta * self.root_depth_m * 1000


@dataclass(frozen=True)
class Weather:
    date: str
    rain_mm: float
    eto_mm: float
    tmin_c: float
    tmax_c: float

    def __post_init__(self) -> None:
        if not all(isfinite(v) for v in (self.rain_mm, self.eto_mm, self.tmin_c, self.tmax_c)):
            raise ValueError("Weather values must be finite")
        if self.rain_mm < 0 or self.eto_mm < 0 or self.tmin_c > self.tmax_c:
            raise ValueError("Invalid rainfall, ET0, or temperature")


@dataclass(frozen=True)
class Flux:
    next_storage_mm: float
    actual_et_mm: float
    runoff_mm: float
    drainage_mm: float
    stress: float
    residual_mm: float


def water_step(storage_mm: float, rain_mm: float, irrigation_mm: float, eto_mm: float, soil: Soil) -> Flux:
    """Conserve daily root-zone mass; excess above saturation leaves as runoff.

    ET is limited by water above wilting. Water above field capacity drains.
    This simple fixed-root model is a surrogate, not AquaCrop calibration.
    """
    values = (storage_mm, rain_mm, irrigation_mm, eto_mm)
    if not all(isfinite(v) for v in values) or min(rain_mm, irrigation_mm, eto_mm) < 0:
        raise ValueError("Water inputs must be finite and nonnegative")
    minimum, capacity, maximum = (soil.mm(x) for x in (soil.wilting, soil.field_capacity, soil.saturation))
    if not minimum <= storage_mm <= maximum:
        raise ValueError("Initial root-zone storage is outside soil bounds")
    incoming = storage_mm + rain_mm + irrigation_mm
    runoff = max(0.0, incoming - maximum)
    available = min(incoming, maximum)
    relative = min(1.0, max(0.0, (available - minimum) / (capacity - minimum)))
    demand = eto_mm * 1.05
    actual_et = min(max(0.0, available - minimum), demand * relative)
    after_et = available - actual_et
    drainage = max(0.0, after_et - capacity) * 0.55
    next_storage = after_et - drainage
    residual = storage_mm + rain_mm + irrigation_mm - actual_et - runoff - drainage - next_storage
    if abs(residual) > 1e-8:
        raise ArithmeticError("Root-zone mass balance failed")
    return Flux(next_storage, actual_et, runoff, drainage, 1 - relative, residual)


def correct_belief(mean_mm: float, variance_mm2: float, measured_mm: float, sensor_variance_mm2: float) -> tuple[float, float]:
    if min(variance_mm2, sensor_variance_mm2) < 0 or not all(isfinite(x) for x in (mean_mm, variance_mm2, measured_mm, sensor_variance_mm2)):
        raise ValueError("Invalid belief or sensor variance")
    denominator = variance_mm2 + sensor_variance_mm2
    gain = variance_mm2 / denominator if denominator else 0.0
    return mean_mm + gain * (measured_mm - mean_mm), (1 - gain) * variance_mm2


def feasible_action(proposed_mm: float, daily_max_mm: float, remaining_mm: float) -> float:
    if not all(isfinite(v) for v in (proposed_mm, daily_max_mm, remaining_mm)) or min(daily_max_mm, remaining_mm) < 0:
        raise ValueError("Invalid irrigation constraints")
    return min(max(0.0, proposed_mm), daily_max_mm, remaining_mm)


def _values(states: list[float], actions: list[float], soil: Soil, forecast: Weather) -> list[list[float]]:
    # The same one-day objective and forecast is used for every state/action.
    result = []
    for state in states:
        row = []
        for action in actions:
            flux = water_step(state, forecast.rain_mm, action, forecast.eto_mm, soil)
            expected_depletion = max(0.0, soil.mm(soil.field_capacity) - flux.next_storage_mm)
            row.append(-0.25 * action - 0.16 * expected_depletion - 12.0 * flux.stress)
        result.append(row)
    return result


def _regret(matrix: list[list[float]], weights: list[float]) -> tuple[int, float]:
    weighted = [sum(w * row[a] for w, row in zip(weights, matrix)) for a in range(len(matrix[0]))]
    choice = max(range(len(weighted)), key=weighted.__getitem__)
    regret = sum(w * (max(row) - row[choice]) for w, row in zip(weights, matrix))
    if regret < -1e-8:
        raise ArithmeticError("Negative estimated regret")
    return choice, max(0.0, regret)


def carat_decision(mean_mm: float, std_mm: float, soil: Soil, forecast: Weather, actions_mm: list[float], observations_left: int, sensor_std_mm: float, seed: int, observation_cost: float = 0.15, samples: int = 16) -> dict:
    """Approximate conditional regret and VOI without hidden reference state."""
    if not actions_mm or observations_left < 0 or std_mm < 0 or sensor_std_mm < 0 or samples < 1:
        raise ValueError("Invalid CARAT configuration")
    rng = Random(seed)
    low, high = soil.mm(soil.wilting), soil.mm(soil.saturation)
    states = [min(high, max(low, mean_mm + rng.gauss(0, std_mm))) for _ in range(20)]
    matrix = _values(states, actions_mm, soil, forecast)
    weights = [1 / len(states)] * len(states)
    choice, before = _regret(matrix, weights)
    after_total = 0.0
    sigma2 = max(sensor_std_mm ** 2, 1e-9)
    for _ in range(samples):
        z = states[rng.randrange(len(states))] + rng.gauss(0, sensor_std_mm)
        likelihood = [exp(-0.5 * (z - state) ** 2 / sigma2) for state in states]
        total = sum(likelihood)
        posterior = [x / total for x in likelihood] if total > 1e-300 else weights
        _, regret_after = _regret(matrix, posterior)
        after_total += regret_after
    gross = before - after_total / samples
    net = gross - observation_cost
    return {"proposed_mm": actions_mm[choice], "regret_before": before, "expected_regret_after": after_total / samples, "gross_voi": gross, "net_voi": net, "observe": observations_left > 0 and net > 0, "plausible_states_mm": states, "candidate_actions_mm": actions_mm}


def simulate(weather: list[Weather], soil: Soil, budget_mm: float, daily_max_mm: float, observation_budget: int, controller: str = "fixed", seed: int = 42) -> tuple[list[dict], dict]:
    """Run a seeded season. Hidden storage is accessed only after action selection."""
    if not weather or budget_mm < 0 or daily_max_mm < 0 or observation_budget < 0:
        raise ValueError("Invalid simulation setup")
    if controller not in {"fixed", "threshold", "deficit", "conservative", "carat"}:
        raise ValueError("Unsupported controller")
    rng = Random(seed)
    truth = soil.mm(soil.field_capacity * 0.85)
    estimate = soil.mm(soil.field_capacity * 0.82)
    variance = 8.0 ** 2
    used, observed, stress_sum = 0.0, 0, 0.0
    rows = []
    previous_rain = 0.0
    for day, actual in enumerate(weather):
        # A deterministic past-based forecast; the actual day's weather is not read here.
        forecast = Weather(actual.date, previous_rain * 0.6, 4.5, 23, 33)
        remaining = budget_mm - used
        actions = sorted(set(feasible_action(a, daily_max_mm, remaining) for a in (0, 5, 10, 15, 20)))
        decision = None
        if controller == "fixed":
            proposed = 10.0 if day % 3 == 0 else 0.0
        elif controller == "threshold":
            proposed = 15.0 if estimate < soil.mm(soil.field_capacity * 0.8) else 0.0
        elif controller == "deficit":
            # A lower refill threshold deliberately protects the seasonal budget.
            proposed = 12.0 if estimate < soil.mm(soil.field_capacity * 0.7) else 0.0
        elif controller == "conservative":
            # A simple high-security threshold for stress-sensitive crops.
            proposed = 10.0 if estimate < soil.mm(soil.field_capacity * 0.88) else 0.0
        else:
            decision = carat_decision(estimate, sqrt(variance), soil, forecast, actions, observation_budget - observed, soil.root_depth_m * 1000 * 0.02, seed + day)
            proposed = decision["proposed_mm"]
            if decision["observe"]:
                measurement = truth + rng.gauss(0, soil.root_depth_m * 1000 * 0.02)
                estimate, variance = correct_belief(estimate, variance, measurement, (soil.root_depth_m * 1000 * 0.02) ** 2)
                observed += 1
                decision["measurement_mm"] = measurement
        applied = feasible_action(proposed, daily_max_mm, remaining)
        # Forecast propagates belief; realized weather advances hidden reference only now.
        predicted = water_step(estimate, forecast.rain_mm, applied, forecast.eto_mm, soil)
        estimate = predicted.next_storage_mm
        variance = min(400.0, variance + 9.0)
        actual_flux = water_step(truth, actual.rain_mm, applied, actual.eto_mm, soil)
        truth = actual_flux.next_storage_mm
        used += applied
        stress_sum += actual_flux.stress
        previous_rain = actual.rain_mm
        rows.append({"day": day + 1, "date": actual.date, "rain_mm": actual.rain_mm, "eto_mm": actual.eto_mm, "proposed_mm": proposed, "irrigation_mm": applied, "estimated_storage_mm": estimate, "estimate_std_mm": sqrt(variance), "reference_storage_mm_evaluation_only": truth, "stress_proxy": actual_flux.stress, "runoff_mm": actual_flux.runoff_mm, "drainage_mm": actual_flux.drainage_mm, "mass_balance_residual_mm": actual_flux.residual_mm, "observation": decision})
    summary = {"days": len(rows), "seasonal_irrigation_mm": used, "observations_used": observed, "cumulative_stress_proxy": stress_sum, "yield_proxy_t_ha": 7.0 * max(0.0, 1 - stress_sum / len(rows)), "twin_rmse_mm": sqrt(sum((r["estimated_storage_mm"] - r["reference_storage_mm_evaluation_only"]) ** 2 for r in rows) / len(rows)), "provenance": "synthetic demonstration; simulated reference; yield is an uncalibrated proxy"}
    return rows, summary
