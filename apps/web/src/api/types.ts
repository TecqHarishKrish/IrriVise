/** Types mirroring the IrriVise REST API (/api/v1). */
export interface Health {
  api: string; database: string; schema_revision: string;
  worker: { status: 'online' | 'offline' | 'not_started'; message?: string; last_seen_seconds_ago?: number; running_jobs?: number };
  datasets: number; sample_dataset: boolean; models: number; runs: number; active_jobs: number;
  aquacrop: { available: boolean; detail: string }; mode: string;
}
export interface Project { id: string; name: string; description: string; crop: string; is_sample: boolean; archived: boolean; created_at: string; updated_at: string; scenario_count?: number }
export interface Scenario {
  id: string; project_id: string; name: string; latitude: number; longitude: number; crop_profile: string; soil_profile: string;
  planting_mmdd: string; daily_max_mm: number; seasonal_budget_mm: number; observation_budget: number; sensor_noise_m3m3: number;
  sensor_mode: string; initial_fraction_mean: number; dataset_id: string | null; validation_status: string; validation_messages: string[];
  archived: boolean; advanced: Record<string, Record<string, unknown>>; season_length_days: number | null; scenario_sha256?: string;
  resolved_config?: Record<string, unknown>; config_error?: string; created_at: string; updated_at: string;
}
export interface Dataset {
  id: string; name: string; source: 'sample' | 'uploaded' | 'nasa_power'; rows: number; start: string; end: string; latitude: number | null; longitude: number | null;
  time_standard: string; checksum_sha256: string; units: Record<string, string>; validation: ValidationReport; provenance: Record<string, unknown>;
  license: string; created_at: string; is_synthetic: boolean;
}
export interface ValidationReport { rows: number; start: string; end: string; ok: boolean; errors: string[]; warnings: string[]; quarantined_count: number; quarantined_dates: string[]; missing_dates: number; missingness_pct: Record<string, number> }
export interface WeatherRow { date: string; rain_mm: number; eto_mm: number; tmin_c: number; tmax_c: number }
export interface SeasonInfo { season_id: string; start: string; end?: string; rain_mm: number; eto_mm?: number; split: 'train' | 'validation' | 'test' }
export interface Split { train: string[]; validation: string[]; test: string[]; rule: string }
export interface DatasetPreview { dataset: Dataset; series: WeatherRow[]; series_decimated: boolean; yearly_totals: { year: number; rain_mm: number; eto_mm: number; days: number }[]; seasons: SeasonInfo[]; skipped_seasons: string[]; split: Split; head: WeatherRow[] }
export interface Job {
  id: string; kind: 'weather_fetch' | 'simulation' | 'training' | 'experiment'; status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted';
  phase: string; progress: number; current_step: number; total_steps: number; cancel_requested: boolean; payload: Record<string, unknown>;
  result: Record<string, unknown>; error: string | null; scenario_id: string | null; created_at: string; started_at: string | null; finished_at: string | null;
  last_sequence: number; log_excerpt?: JobEvent[];
}
export interface JobEvent { sequence: number; job_id: string; status: string; phase: string; current_step: number; total_steps: number; metric_name: string | null; metric_value: number | null; timestamp: string; message: string; data: Record<string, unknown> | null }
export interface MethodSpec { key: string; code: string; label: string; irrigation: string; observation: string; correction: boolean; soft_risk: boolean; needs_model: boolean; role: string; note: string }
export interface Defaults {
  actions_mm: number[]; crops: Record<string, Record<string, unknown>>; soils: Record<string, { name: string; theta_wp: number; theta_fc: number; theta_sat: number; source: string }>;
  training_presets: Record<string, TrainingPreset>; carat: Record<string, number | string>; uncertainty: Record<string, number>; risk: Record<string, number | boolean>; reward: Record<string, number>;
  methods: MethodSpec[]; sensor_modes: string[]; feature_spec_version: string; policy_features: { name: string; description: string }[]; units: Record<string, string>;
}
export interface TrainingPreset { preset: string; total_timesteps: number; seeds: number[]; eval_freq_steps: number; early_stop_evals: number; max_wall_seconds: number; hyperparameters: Record<string, number | number[]> }
export interface RunSummary {
  method: string; method_code: string; method_label: string; days: number; seasonal_irrigation_mm: number; seasonal_rain_mm: number; irrigation_events: number;
  yield_ratio_proxy: number; yield_proxy_t_ha: number; irrigation_wp_proxy_kg_m3: number | null; total_wp_proxy_kg_m3: number | null; cumulative_stress: number;
  weighted_stress: number; stress_days: number; observation_count: number; observation_attempts: number; observations_remaining: number; observation_use_rate: number | null;
  twin_rmse_mm: number; twin_rmse_m3m3: number; twin_bias_mm: number; estimated_regret_mean: number | null; gross_voi_mean: number | null; net_voi_mean: number | null;
  decision_disagreement_rate: number | null; total_reward: number; objective_with_observation_cost: number; max_daily_violations: number; season_budget_violations: number;
  runtime_seconds: number; yield_label: string;
  aquacrop?: { aquacrop_simulated_dry_yield_t_ha?: number; aquacrop_seasonal_irrigation_mm?: number; harvest_date?: string; label?: string; error?: string } | null;
}
export interface Run { id: string; job_id: string; scenario_id: string; dataset_id: string; season_id: string; split: string; method: string; method_code: string; method_label: string; model_id: string | null; seed: number; summary: RunSummary; created_at: string; manifest?: Record<string, unknown> }
export interface DailyRow {
  day: number; date: string; stage: number; kc: number; ky: number; rain_mm: number; rain_observed_mm: number; eto_mm: number; forecast_rain_mm: number; forecast_eto_mm: number;
  belief_mean_mm: number; belief_std_mm: number; belief_q10_mm: number; belief_q90_mm: number; belief_theta: number; est_depletion_fraction: number; est_ks: number;
  taw_mm: number; raw_mm: number; root_depth_m: number; initial_action_mm: number; observed: boolean; observation_attempted: boolean; measurement_status: string | null;
  measurement_theta: number | null; corrected_mean_mm: number | null; corrected_std_mm: number | null; proposed_mm: number; applied_mm: number; constraint_status: string;
  risk_flags: string | null; est_regret: number | null; gross_voi: number | null; net_voi: number | null; remaining_water_mm: number; remaining_observations: number;
  end_belief_mean_mm: number; end_belief_std_mm: number;
}
export interface TruthRow { day: number; date: string; true_storage_mm: number; true_theta: number; true_ks: number; estimate_end_mm: number; estimate_error_mm: number; runoff_mm: number; drainage_mm: number; actual_et_mm: number; crop_et_mm: number }
export interface Assessment {
  day: number; candidate_actions_mm: number[]; expected_values: number[]; prob_action_best: number[]; belief_action_mm: number; policy_action_mm: number | null;
  regret_before: number; regret_policy_action: number | null; expected_regret_after: number; gross_voi: number; observation_cost: number; shadow_price: number | null;
  net_voi: number; observe_recommended: boolean; reason: string; states_agree: boolean;
  plausible_states?: { member: number; storage_mm: number; theta_m3m3: number; weight: number; best_action_mm: number; q_values: number[] }[];
  diagnostics: Record<string, unknown>;
}
export interface BeliefSummary { mean_storage_mm: number; std_storage_mm: number; q10_storage_mm: number; q90_storage_mm: number; mean_theta: number; depletion_fraction: number; taw_mm: number; raw_mm: number; ks_estimate: number; days_since_observation: number; root_depth_m: number }
export interface DecisionTrace {
  day: number; date: string; stage: number; initial_belief: BeliefSummary; forecast: { rain_mm: number[]; eto_mm: number[]; source: string; confidence: string };
  initial_action_mm: number; observation_policy: string; observe: boolean; observe_reason: string;
  measurement: { status: string; theta_m3m3: number | null; noise_std_m3m3: number; charged: boolean; flags: string[]; state_day: number | null } | null;
  correction: { applied: boolean; reason: string; gain: number; prior_mean_mm: number; posterior_mean_mm: number; prior_var_mm2: number; posterior_var_mm2: number; innovation_mm: number; measurement_mm: number } | null;
  corrected_belief: BeliefSummary | null; assessment_before: Assessment | null; assessment_after: Assessment | null; proposed_mm: number;
  risk: { proposed_mm: number; hard_projected_mm: number; applied_mm: number; constraint_status: string; reasons: string[]; risk_flags: string[]; stress_probability: Record<string, number>; predicted_stress_quantiles: Record<string, number>; soft_layer_enabled: boolean };
  applied_mm: number; budgets: { water_remaining_before_mm: number; water_remaining_after_mm: number; observations_remaining: number; observations_used: number };
}
export interface ModelRecord { id: string; job_id: string; scenario_id: string; preset: string; seed: number; actual_timesteps: number; checkpoint_sha256: string; validation: Record<string, number>; selected: boolean; research_quality: boolean; status: string; created_at: string; manifest?: ModelManifest; checkpoint_bytes?: number | null }
export interface ModelManifest { history: { timesteps: number; train_mean_episode_reward: number | null; validation_mean_reward?: number; validation_mean_yield_ratio_proxy?: number; validation_mean_irrigation_mm?: number; checkpoint_saved?: boolean }[]; train_seasons: string[]; validation_seasons: string[]; stop_reason: string; selection: string; wall_seconds: number; training_config: Record<string, unknown>; final_validation: Record<string, number> | null }
export interface Stat { n: number; mean: number | null; std: number | null; min?: number; max?: number; ci95: [number, number] | null }
export interface Paired { n_pairs: number; mean_difference?: number; median_difference?: number; ci95?: [number, number] | null; wins?: number; losses?: number; ties?: number; wilcoxon_p?: number | null; status: string }
export interface ExperimentTableRow { method: string; code: string; label: string; role: string; runs: number; failed_runs: number; [metric: string]: Stat | string | number }
export interface Experiment {
  id: string; name: string; scenario_id: string; model_id: string | null; status: string; job_id: string | null; progress: number | null; error: string | null;
  config: { methods: string[]; reference_method: string; split: string; seeds: number[]; observation_budgets: number[]; sensor_noise_m3m3: number[]; sensor_mode: string; aquacrop: boolean };
  created_at: string; n_runs?: number; n_failed?: number; planned_runs?: number;
  summary?: { table: ExperimentTableRow[]; paired_vs_reference: Record<string, Record<string, Paired & Partial<Stat>>>; narrative: string[]; n_runs: number; n_failed: number; failures: { method: string; error: string; season_id: string; seed: number }[]; hard_constraint_violations: number; runtime_seconds: number };
  manifest?: Record<string, unknown>;
}
export interface ExportRecord { id: string; source_type: string; source_id: string; format: string; sha256: string; bytes: number; created_at: string; download_url: string }
export interface AnalyticsOverview { total_runs: number; methods: ({ method: string; code: string; label: string; runs: number } & Record<string, Stat | string | number>)[]; note: string }
export interface Diagnostics { health: Health; cpu_count: number; memory: { total_bytes: number; available_bytes: number | null }; disk: { free_bytes: number; artifacts_bytes: number; quota_bytes: number }; paths: Record<string, string>; limits: Record<string, number>; packages: Record<string, string> }
