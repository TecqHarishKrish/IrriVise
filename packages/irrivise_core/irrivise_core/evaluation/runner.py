"""Episode runner: executes one season for one method and records auditable traces.

Per day (CARAT pseudocode, master spec §8.6):
    forecast ← past observations only
    initial action ← irrigation policy(view before reading)
    assessment ← CARAT regret / VOI on the current belief (diagnostic for all methods,
                 VOI computed only when the observation policy needs it)
    observe? ← observation policy
    if observe: one budgeted reading → (optional) twin correction → re-assess, re-propose
    applied ← risk manager (hard limits always; soft layer per method)
    hidden farm advances with realized weather; twin propagates with observed weather

Outputs are split by permission:
* ``daily``      operational trace (no hidden state) — safe for decision views
* ``decisions``  CARAT decision traces (no hidden state)
* ``truth``      EVALUATION-ONLY hidden reference trace
* ``summary``    metrics computed after the run by the evaluator
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ..baselines.policies import METHODS, FixedSchedulePolicy, MethodSpec, SoilThresholdPolicy, observation_policy
from ..carat.engine import CaratEngine
from ..carat.risk import RiskManager
from ..config.schemas import ScenarioConfig
from ..data.weather import Season
from ..envs.reward import daily_reward, terminal_reward
from ..simulation.forecast import ClimatologyForecaster
from ..simulation.world import FieldWorld
from ..util.repro import rng as make_rng
from .metrics import compute_summary


@dataclass
class EpisodeResult:
    method: str
    season_id: str
    world_seed: int
    daily: list[dict]
    decisions: list[dict]
    truth: list[dict]
    summary: dict
    hidden_parameters: dict = field(default_factory=dict)


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def run_episode(scenario: ScenarioConfig, season: Season, forecaster: ClimatologyForecaster, world_seed: int, method: str | MethodSpec,
                ppo_policy=None, uncertainty_threshold: float = 0.08, record_states: bool = True,
                carat_diagnostics: bool = True) -> EpisodeResult:
    spec = METHODS[method] if isinstance(method, str) else method
    if spec.needs_model and ppo_policy is None:
        raise ValueError(f"Method '{spec.key}' requires a trained PPO model; train one or choose a non-PPO baseline")
    started = time.perf_counter()
    world = FieldWorld(scenario, season, forecaster, world_seed)
    carat = CaratEngine(scenario)
    risk = RiskManager(scenario, soft_enabled=spec.soft_risk)
    obs_policy = observation_policy(spec.observation, uncertainty_threshold)
    obs_rng = make_rng(world_seed, season.season_id, "observation-policy")
    voi_rng = make_rng(world_seed, season.season_id, "carat-hypothetical", spec.key)
    if spec.irrigation == "fixed":
        irrigation = FixedSchedulePolicy()
    elif spec.irrigation == "threshold":
        irrigation = SoilThresholdPolicy(scenario)
    elif spec.irrigation == "ppo":
        irrigation = ppo_policy
    else:
        irrigation = None  # lookahead planner: belief action from the assessment
    daily, decisions, truth = [], [], []
    total_reward = 0.0
    need_assessment = carat_diagnostics or obs_policy.needs_voi or irrigation is None
    while not world.done:
        day = world.day
        forecast = world.forecast()
        view = world.view(forecast)
        members = world.members()
        initial = irrigation.propose(view) if irrigation is not None else None
        assessment = None
        if need_assessment:
            assessment = carat.assess(members, forecast, day, world.remaining_water_mm, world.sensor.remaining,
                                      world.sensor.is_available(day), scenario.sensor.noise_std_m3m3, voi_rng,
                                      policy_action_mm=initial, compute_voi=obs_policy.needs_voi)
        if initial is None:
            initial = assessment.belief_action_mm
        observe, obs_reason = obs_policy.decide(view, assessment, obs_rng)
        measurement, correction, after = None, None, None
        final_view, final_members, proposed = view, members, initial
        if observe:
            measurement, correction = world.observe(correct=spec.correction)
            if correction is not None and correction.get("applied"):
                final_view, final_members = world.view(forecast), world.members()
                if need_assessment:
                    after = carat.assess(final_members, forecast, day, world.remaining_water_mm, world.sensor.remaining,
                                         world.sensor.is_available(day), scenario.sensor.noise_std_m3m3, voi_rng,
                                         policy_action_mm=None, compute_voi=False)
                proposed = irrigation.propose(final_view) if irrigation is not None else after.belief_action_mm
        decision = risk.project(proposed, final_members, forecast, day, world.remaining_water_mm)
        remaining_before = world.remaining_water_mm
        farm = world.apply(decision.applied_mm)
        parts = daily_reward(scenario, day, proposed, decision.hard_projected_mm, farm.ks)
        total_reward += parts["reward"]
        end_belief = world.twin.summary()
        b0, b1 = view.belief, final_view.belief
        row = {
            "day": day + 1, "date": season.dates[day], "stage": view.stage, "kc": _r(view.kc), "ky": _r(view.ky),
            "rain_mm": _r(season.rain_mm[day], 3), "rain_observed_mm": _r(world.observed_rain[-1], 3), "eto_mm": _r(season.eto_mm[day], 3),
            "forecast_rain_mm": _r(forecast.rain_mm[0], 3), "forecast_eto_mm": _r(forecast.eto_mm[0], 3),
            "belief_mean_mm": _r(b0.mean_storage_mm), "belief_std_mm": _r(b0.std_storage_mm), "belief_q10_mm": _r(b0.q10_storage_mm),
            "belief_q90_mm": _r(b0.q90_storage_mm), "belief_theta": _r(b0.mean_theta, 5), "est_depletion_fraction": _r(b0.depletion_fraction),
            "est_ks": _r(b0.ks_estimate), "taw_mm": _r(b0.taw_mm), "raw_mm": _r(b0.raw_mm), "root_depth_m": _r(b0.root_depth_m),
            "initial_action_mm": _r(initial, 3), "observed": bool(measurement is not None and measurement.charged),
            "observation_attempted": measurement is not None, "measurement_status": measurement.status if measurement else None,
            "measurement_theta": _r(measurement.theta_m3m3, 5) if measurement and measurement.theta_m3m3 is not None else None,
            "corrected_mean_mm": _r(b1.mean_storage_mm) if correction and correction.get("applied") else None,
            "corrected_std_mm": _r(b1.std_storage_mm) if correction and correction.get("applied") else None,
            "proposed_mm": _r(proposed, 3), "applied_mm": _r(decision.applied_mm, 3), "constraint_status": decision.constraint_status,
            "risk_flags": "|".join(decision.risk_flags), "est_regret": _r(assessment.regret_before, 6) if assessment else None,
            "gross_voi": _r(assessment.gross_voi, 6) if assessment and obs_policy.needs_voi else None,
            "net_voi": _r(assessment.net_voi, 6) if assessment and obs_policy.needs_voi else None,
            "remaining_water_mm": _r(world.remaining_water_mm, 3), "remaining_observations": world.sensor.remaining,
            "end_belief_mean_mm": _r(end_belief.mean_storage_mm), "end_belief_std_mm": _r(end_belief.std_storage_mm),
        }
        daily.append(row)
        trace = {
            "day": day + 1, "date": season.dates[day], "stage": view.stage,
            "initial_belief": b0.as_dict(), "forecast": forecast.as_dict(),
            "initial_action_mm": initial, "observation_policy": spec.observation, "observe": bool(observe), "observe_reason": obs_reason,
            "measurement": measurement.as_dict() if measurement else None, "correction": correction,
            "corrected_belief": b1.as_dict() if correction and correction.get("applied") else None,
            "assessment_before": None, "assessment_after": None,
            "proposed_mm": proposed, "risk": decision.as_dict(), "applied_mm": decision.applied_mm,
            "budgets": {"water_remaining_before_mm": round(remaining_before, 3), "water_remaining_after_mm": round(world.remaining_water_mm, 3),
                        "observations_remaining": world.sensor.remaining, "observations_used": world.sensor.used},
        }
        if assessment is not None:
            a = assessment.as_dict()
            if not record_states:
                a.pop("plausible_states", None)
                a["diagnostics"].pop("hypothetical_regret_after", None)
            trace["assessment_before"] = a
        if after is not None:
            a2 = after.as_dict()
            if not record_states:
                a2.pop("plausible_states", None)
            trace["assessment_after"] = a2
        decisions.append(trace)
        truth.append({"day": day + 1, "date": season.dates[day], "true_storage_mm": _r(farm.storage_mm), "true_theta": _r(farm.theta, 5),
                      "true_ks": _r(farm.ks), "true_depletion_mm": _r(farm.depletion_mm), "true_taw_mm": _r(farm.taw_mm), "root_depth_end_m": _r(farm.root_depth_m, 5),
                      "actual_et_mm": _r(farm.actual_et_mm), "crop_et_mm": _r(farm.crop_et_mm), "runoff_mm": _r(farm.runoff_mm),
                      "drainage_mm": _r(farm.drainage_mm), "mass_balance_residual_mm": float(farm.residual_mm),
                      "estimate_end_mm": _r(end_belief.mean_storage_mm), "estimate_error_mm": _r(end_belief.mean_storage_mm - farm.storage_mm),
                      **{k: _r(v, 5) for k, v in parts.items()}})
    evaluation = world.evaluation_record()
    terminal = terminal_reward(scenario, evaluation["yield_ratio"])
    total_reward += terminal
    runtime = time.perf_counter() - started
    summary = compute_summary(scenario, spec, daily, truth, evaluation, total_reward, terminal, runtime, world.sensor)
    return EpisodeResult(spec.key, season.season_id, world_seed, daily, decisions, truth, summary, evaluation["hidden_parameters"])
