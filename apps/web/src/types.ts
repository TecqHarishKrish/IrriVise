export type Project = { id: string; name: string; crop: string };

export type Scenario = {
  id: string; project_id: string; name: string;
  budget_mm: number; daily_max_mm: number; observation_budget: number;
};

export type Job = {
  id: string; kind: string; status: string; controller: string;
  seed: number; progress: number; current_step: number; total_steps: number;
  run_id: string | null; error: string | null;
};

export type ModelRecord = {
  id?: string; algorithm: string; seed: number; actual_timesteps: number;
  checkpoint: string; checkpoint_sha256?: string; evaluation: string; research_quality: boolean;
};

export type AquaCropResult = {
  aquacrop_simulated_dry_yield_t_ha: number;
  aquacrop_seasonal_irrigation_mm: number;
};

export type Run = {
  id: string; controller: string; created_at: string;
  summary: {
    days: number; seasonal_irrigation_mm: number; observations_used: number;
    cumulative_stress_proxy: number; yield_proxy_t_ha: number; twin_rmse_mm: number;
    provenance: string; dataset_source?: string; dataset_id?: string;
    aquacrop?: AquaCropResult; seed?: number;
  };
};

export type Day = {
  day: number; date: string; rain_mm: number; eto_mm?: number; irrigation_mm: number;
  estimated_storage_mm: number; estimate_std_mm?: number;
  reference_storage_mm_evaluation_only: number;
  stress_proxy: number; runoff_mm?: number; drainage_mm?: number;
  observation?: {
    observe: boolean; regret_before: number; gross_voi: number; net_voi: number;
    proposed_mm: number; measurement_mm?: number;
  } | null;
};

export type Dataset = {
  id: string; source: string; days: number;
  start: string; end: string; checksum_sha256: string;
};

export type ExperimentResult = {
  id: string; scenario_id: string; created_at: string;
  controllers: string[]; seed: number; status: string;
  results: Array<{
    controller: string; seasonal_irrigation_mm: number; yield_proxy_t_ha: number;
    cumulative_stress_proxy: number; observations_used: number;
    aquacrop_simulated_dry_yield_t_ha?: number; run_id: string;
  }>;
};

export type Access = { id: string; email: string; role: 'admin' | 'user'; features: string[] };

export type { DataReturn } from './hooks/useData';
