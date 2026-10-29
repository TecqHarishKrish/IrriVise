"""Matched benchmark experiments and ablations.

Matching: every method is run on exactly the same (season, world seed,
observation budget, sensor noise) cells. Hidden farm parameters, gauge errors
and sensor noise streams are derived from (world seed, season) only, so all
methods face the same hidden truth (common random numbers). Results are
re-derived from per-run summaries that are themselves computed from traces.
"""
from __future__ import annotations

import time
from typing import Callable, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..baselines.policies import METHODS
from ..config.schemas import ScenarioConfig
from ..data.weather import Season
from ..simulation.forecast import ClimatologyForecaster
from .runner import run_episode
from .stats import describe, paired_difference

HIGHER_IS_BETTER = {"yield_proxy_t_ha": True, "aquacrop_yield_t_ha": True, "irrigation_wp_proxy_kg_m3": True, "total_reward": True,
                    "objective_with_observation_cost": True, "seasonal_irrigation_mm": False, "cumulative_stress": False,
                    "weighted_stress": False, "stress_days": False, "twin_rmse_mm": False, "observation_count": False}


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Baseline comparison", min_length=2, max_length=120)
    methods: list[str] = Field(default_factory=lambda: ["fixed_schedule", "soil_threshold", "ppo", "carat_full"])
    reference_method: str = "fixed_schedule"
    split: Literal["validation", "test"] = "test"
    seeds: list[int] = Field(default_factory=lambda: [1, 2, 3])
    observation_budgets: list[int] = Field(default_factory=lambda: [10])
    sensor_noise_m3m3: list[float] = Field(default_factory=lambda: [0.02])
    sensor_mode: Literal["nominal", "missing", "biased", "stuck", "delayed"] = "nominal"
    uncertainty_threshold: float = Field(default=0.08, gt=0, le=1)
    aquacrop: bool = False
    max_runs: int = Field(default=600, ge=1, le=5000)

    @field_validator("methods")
    @classmethod
    def _methods(cls, value: list[str]) -> list[str]:
        unknown = [m for m in value if m not in METHODS]
        if unknown or not value or len(set(value)) != len(value):
            raise ValueError(f"methods must be unique keys from {sorted(METHODS)}; unknown: {unknown}")
        return value

    @field_validator("seeds")
    @classmethod
    def _seeds(cls, value: list[int]) -> list[int]:
        if not 1 <= len(value) <= 50 or len(set(value)) != len(value) or any(s < 0 for s in value):
            raise ValueError("Provide 1–50 unique nonnegative seeds")
        return value

    @field_validator("observation_budgets")
    @classmethod
    def _budgets(cls, value: list[int]) -> list[int]:
        if not 1 <= len(value) <= 8 or any(not 0 <= b <= 365 for b in value):
            raise ValueError("Provide 1–8 observation budgets in [0, 365]")
        return value

    @field_validator("sensor_noise_m3m3")
    @classmethod
    def _noise(cls, value: list[float]) -> list[float]:
        if not 1 <= len(value) <= 6 or any(not 0 <= n <= 0.2 for n in value):
            raise ValueError("Provide 1–6 sensor noise levels in [0, 0.2] m³/m³")
        return value

    def cells(self, seasons: list[Season]) -> int:
        return len(seasons) * len(self.seeds) * len(self.observation_budgets) * len(self.sensor_noise_m3m3)


def run_experiment(config: ExperimentConfig, base: ScenarioConfig, seasons: list[Season], forecaster: ClimatologyForecaster,
                   ppo_policy_factory: Callable[[ScenarioConfig], object] | None = None,
                   aquacrop_fn: Callable[[Season, list[float]], dict] | None = None,
                   progress: Callable[[int, int, str], None] | None = None, cancelled: Callable[[], bool] | None = None) -> dict:
    if not seasons:
        raise ValueError(f"No {config.split} seasons available for this dataset; evaluation cannot fall back to training seasons")
    if config.reference_method not in config.methods:
        raise ValueError("reference_method must be one of the selected methods")
    needs_model = [m for m in config.methods if METHODS[m].needs_model]
    if needs_model and ppo_policy_factory is None:
        raise ValueError(f"Methods {needs_model} require a trained PPO model")
    total = config.cells(seasons) * len(config.methods)
    if total > config.max_runs:
        raise ValueError(f"Experiment would execute {total} runs (cap {config.max_runs}); reduce seeds/budgets/methods")
    rows, failures = [], []
    started = time.monotonic()
    done = 0
    for budget in config.observation_budgets:
        for noise in config.sensor_noise_m3m3:
            sensor = base.sensor.model_copy(update={"noise_std_m3m3": noise, "mode": config.sensor_mode})
            scenario = base.model_copy(update={"observation_budget": budget, "sensor": sensor})
            policy = ppo_policy_factory(scenario) if needs_model else None
            for season in seasons:
                for seed in config.seeds:
                    for method in config.methods:
                        if cancelled and cancelled():
                            raise InterruptedError("Experiment cancelled")
                        cell = {"season_id": season.season_id, "seed": seed, "observation_budget": budget, "sensor_noise_m3m3": noise}
                        try:
                            result = run_episode(scenario, season, forecaster, seed, method, ppo_policy=policy,
                                                 uncertainty_threshold=config.uncertainty_threshold, record_states=False)
                            row = {**cell, **result.summary}
                            if aquacrop_fn is not None:
                                try:
                                    aq = aquacrop_fn(season, [d["applied_mm"] for d in result.daily])
                                    row["aquacrop_yield_t_ha"] = aq["aquacrop_simulated_dry_yield_t_ha"]
                                    row["aquacrop_irrigation_mm"] = aq["aquacrop_seasonal_irrigation_mm"]
                                except Exception as exc:  # recorded, never hidden
                                    row["aquacrop_error"] = str(exc)[:300]
                            rows.append(row)
                        except Exception as exc:
                            failures.append({**cell, "method": method, "error": f"{type(exc).__name__}: {exc}"[:500]})
                        done += 1
                        if progress:
                            progress(done, total, f"{method} · season {season.season_id} · seed {seed} · budget {budget} · noise {noise}")
    return summarise(config, rows, failures, time.monotonic() - started)


def _water_savings(method_rows: list[dict], reference_rows: list[dict]) -> list[float | None]:
    out = []
    for m, r in zip(method_rows, reference_rows):
        ref = r["seasonal_irrigation_mm"]
        out.append(None if ref <= 0 else 100.0 * (ref - m["seasonal_irrigation_mm"]) / ref)
    return out


def summarise(config: ExperimentConfig, rows: list[dict], failures: list[dict], runtime_s: float) -> dict:
    key = lambda r: (r["season_id"], r["seed"], r["observation_budget"], r["sensor_noise_m3m3"])  # noqa: E731
    by_method: dict[str, dict] = {m: {} for m in config.methods}
    for row in rows:
        by_method[row["method"]][key(row)] = row
    reference = by_method.get(config.reference_method, {})
    metrics = list(HIGHER_IS_BETTER) + ["observation_use_rate", "estimated_regret_mean", "gross_voi_mean", "twin_rmse_m3m3",
                                        "decision_disagreement_rate", "runtime_seconds", "max_daily_violations", "season_budget_violations"]
    table, comparisons = [], {}
    for method in config.methods:
        runs = by_method[method]
        entry = {"method": method, "code": METHODS[method].code, "label": METHODS[method].label, "role": METHODS[method].role,
                 "runs": len(runs), "failed_runs": sum(1 for f in failures if f["method"] == method)}
        for metric in metrics:
            entry[metric] = describe([r.get(metric) for r in runs.values()])
        table.append(entry)
        if method == config.reference_method:
            continue
        common = sorted(set(runs) & set(reference))
        m_rows, r_rows = [runs[c] for c in common], [reference[c] for c in common]
        comp = {metric: paired_difference([r.get(metric) for r in m_rows], [r.get(metric) for r in r_rows], higher)
                for metric, higher in HIGHER_IS_BETTER.items()}
        savings = _water_savings(m_rows, r_rows)
        comp["water_savings_pct"] = describe(savings)
        comp["water_savings_pct"]["note"] = "100·(reference − method)/reference irrigation; undefined when reference irrigation is 0"
        comparisons[method] = comp
    violations = sum(r["max_daily_violations"] + r["season_budget_violations"] for r in rows)
    result = {"config": config.model_dump(), "n_runs": len(rows), "n_failed": len(failures), "failures": failures[:200],
              "table": table, "paired_vs_reference": comparisons, "hard_constraint_violations": violations,
              "runtime_seconds": round(runtime_s, 2)}
    result["narrative"] = narrative(config, table, comparisons, failures)
    result["rows"] = rows
    return result


def narrative(config: ExperimentConfig, table: list[dict], comparisons: dict, failures: list[dict]) -> list[str]:
    """Deterministic 'What did the data show?' sentences generated from the numbers above.

    Differences are always "method − reference". Results are flagged as negative *for the proposed
    method* (role 'proposed'), whichever side of the comparison it is on.
    """
    lines = []
    ref = config.reference_method
    proposed = {m for m in config.methods if METHODS[m].role == "proposed"}
    n_cells = max((t["runs"] for t in table), default=0)
    lines.append(f"{len(table)} methods were run on {n_cells} matched cell(s) each (split: {config.split}; seeds: {len(config.seeds)}). "
                 "All outcomes are simulated; yields are FAO-33 proxies unless an AquaCrop column is shown. Differences are method − reference.")
    for method, comp in comparisons.items():
        label = next(t["label"] for t in table if t["method"] == method)
        y, w, s, o = comp["yield_proxy_t_ha"], comp["seasonal_irrigation_mm"], comp["cumulative_stress"], comp["objective_with_observation_cost"]
        if y.get("n_pairs", 0) == 0:
            lines.append(f"{label}: no paired runs with {ref}.")
            continue
        parts = [f"{label} vs {ref}: irrigation {w['mean_difference']:+.1f} mm ({w['status']})",
                 f"yield proxy {y['mean_difference']:+.3f} t/ha ({y['status']})",
                 f"cumulative stress {s['mean_difference']:+.2f} ({s['status']})",
                 f"objective {o['mean_difference']:+.3f} ({o['status']})"]
        lines.append("; ".join(parts) + f"; n = {y['n_pairs']} pairs.")
        for metric, name in ((y, "yield proxy"), (o, "objective")):
            if not metric.get("ci95"):
                continue
            method_better = metric["ci95"][0] > 0
            method_worse = metric["ci95"][1] < 0
            if (method in proposed and method_worse) or (ref in proposed and method_better):
                winner, loser = (ref, method) if method_worse else (method, ref)
                lines.append(f"Negative result for the proposed method: {winner} beat {loser} on {name} with the CI excluding zero.")
    if any(t["runs"] < 5 for t in table):
        lines.append("Caution: fewer than 5 paired runs for at least one method — treat differences as descriptive, not conclusive.")
    if failures:
        lines.append(f"{len(failures)} run(s) failed and are listed with their errors; they are excluded from statistics.")
    lines.append("These results come from a simulated reference farm and do not demonstrate field performance.")
    return lines
