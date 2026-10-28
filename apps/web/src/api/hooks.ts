import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, del, patch, post } from './client';
import type {
  AnalyticsOverview, Dataset, DatasetPreview, DecisionTrace, Defaults, Diagnostics, Experiment, ExportRecord, Health, Job, ModelRecord, Project, Run,
  Scenario, SeasonInfo, Split, DailyRow, TruthRow,
} from './types';

const ACTIVE = (jobs?: Job[]) => jobs?.some((j) => j.status === 'queued' || j.status === 'running');

export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: () => api<Health>('/health'), refetchInterval: 10_000 });
export const useDefaults = () => useQuery({ queryKey: ['defaults'], queryFn: () => api<Defaults>('/config/defaults'), staleTime: Infinity });
export const useDiagnostics = () => useQuery({ queryKey: ['diagnostics'], queryFn: () => api<Diagnostics>('/system/diagnostics') });
export const useProjects = (includeArchived = false) =>
  useQuery({ queryKey: ['projects', includeArchived], queryFn: () => api<Project[]>(`/projects?include_archived=${includeArchived}`) });
export const useScenarios = (projectId?: string | null, includeArchived = false) =>
  useQuery({ queryKey: ['scenarios', projectId, includeArchived], enabled: !!projectId, queryFn: () => api<Scenario[]>(`/projects/${projectId}/scenarios?include_archived=${includeArchived}`) });
export const useScenario = (id?: string | null) => useQuery({ queryKey: ['scenario', id], enabled: !!id, queryFn: () => api<Scenario>(`/scenarios/${id}`) });
export const useSeasons = (id?: string | null) =>
  useQuery({ queryKey: ['seasons', id], enabled: !!id, queryFn: () => api<{ seasons: SeasonInfo[]; split: Split | null; skipped: string[]; season_length_days?: number; message?: string }>(`/scenarios/${id}/seasons`) });
export const useDatasets = () => useQuery({ queryKey: ['datasets'], queryFn: () => api<Dataset[]>('/datasets') });
export const useDatasetPreview = (id?: string | null, planting = '06-15', length = 140) =>
  useQuery({ queryKey: ['dataset-preview', id, planting, length], enabled: !!id, queryFn: () => api<DatasetPreview>(`/datasets/${id}/preview?planting_mmdd=${planting}&season_length_days=${length}`) });
export const useJobs = (filter = '') => {
  return useQuery({ queryKey: ['jobs', filter], queryFn: () => api<Job[]>(`/jobs?limit=50${filter}`), refetchInterval: (q) => (ACTIVE(q.state.data) ? 2000 : 10_000) });
};
export const useJob = (id?: string | null) =>
  useQuery({ queryKey: ['job', id], enabled: !!id, queryFn: () => api<Job>(`/jobs/${id}`), refetchInterval: (q) => (q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 2000 : false) });
export const useRuns = (scenarioId?: string | null) =>
  useQuery({ queryKey: ['runs', scenarioId ?? 'all'], queryFn: () => api<Run[]>(`/simulations?limit=200${scenarioId ? `&scenario_id=${scenarioId}` : ''}`) });
export const useRun = (id?: string | null) => useQuery({ queryKey: ['run', id], enabled: !!id, queryFn: () => api<Run>(`/simulations/${id}`) });
export const useDaily = (id?: string | null) =>
  useQuery({ queryKey: ['daily', id], enabled: !!id, queryFn: () => api<{ total: number; rows: DailyRow[] }>(`/simulations/${id}/daily?limit=2000`) });
export const useDecisions = (id?: string | null, day?: number | null) =>
  useQuery({ queryKey: ['decision', id, day], enabled: !!id && !!day, queryFn: () => api<{ total: number; rows: DecisionTrace[] }>(`/simulations/${id}/decisions?day=${day}`) });
export const useEvaluation = (id: string | null | undefined, enabled: boolean) =>
  useQuery({ queryKey: ['evaluation', id], enabled: !!id && enabled, queryFn: () => api<{ label: string; hidden_parameters: Record<string, number>; rows: TruthRow[] }>(`/simulations/${id}/evaluation`) });
export const useModels = (scenarioId?: string | null) =>
  useQuery({ queryKey: ['models', scenarioId ?? 'all'], queryFn: () => api<ModelRecord[]>(`/models${scenarioId ? `?scenario_id=${scenarioId}` : ''}`) });
export const useModel = (id?: string | null) => useQuery({ queryKey: ['model', id], enabled: !!id, queryFn: () => api<ModelRecord>(`/models/${id}`) });
export const useExperiments = (scenarioId?: string | null) =>
  useQuery({ queryKey: ['experiments', scenarioId ?? 'all'], queryFn: () => api<Experiment[]>(`/experiments${scenarioId ? `?scenario_id=${scenarioId}` : ''}`),
    refetchInterval: (q) => (q.state.data?.some((e) => e.status === 'queued' || e.status === 'running') ? 3000 : false) });
export const useExperiment = (id?: string | null) =>
  useQuery({ queryKey: ['experiment', id], enabled: !!id, queryFn: () => api<Experiment>(`/experiments/${id}`),
    refetchInterval: (q) => (q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 3000 : false) });
export const useExports = () => useQuery({ queryKey: ['exports'], queryFn: () => api<ExportRecord[]>('/exports') });
export const useAnalytics = (scenarioId?: string | null) =>
  useQuery({ queryKey: ['analytics', scenarioId ?? 'all'], queryFn: () => api<AnalyticsOverview>(`/analytics/overview${scenarioId ? `?scenario_id=${scenarioId}` : ''}`) });

export function useInvalidate() {
  const qc = useQueryClient();
  return (...keys: string[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}

export function useApiMutation<TBody, TResult>(fn: (body: TBody) => Promise<TResult>, invalidate: string[] = []) {
  const refresh = useInvalidate();
  return useMutation({ mutationFn: fn, onSuccess: () => refresh(...invalidate) });
}

export const mutations = {
  createProject: (b: { name: string; description: string }) => post<Project>('/projects', b),
  updateProject: (b: { id: string; name?: string; description?: string; archived?: boolean }) => patch<Project>(`/projects/${b.id}`, { name: b.name, description: b.description, archived: b.archived }),
  archiveProject: (id: string) => del<Project>(`/projects/${id}`),
  sampleProject: () => post<{ project: Project; scenario: Scenario }>('/projects/sample'),
  createScenario: ({ projectId, ...b }: Record<string, unknown> & { projectId: string }) => post<Scenario>(`/projects/${projectId}/scenarios`, b),
  updateScenario: ({ id, ...b }: Record<string, unknown> & { id: string }) => patch<Scenario>(`/scenarios/${id}`, b),
  simulate: (b: { scenario_id: string; method: string; model_id?: string | null; season_id?: string | null; seed: number; aquacrop: boolean }) => post<Job>('/simulations', b),
  train: (b: Record<string, unknown>) => post<Job & { resolved_config: Record<string, unknown> }>('/training', b),
  experiment: (b: Record<string, unknown>) => post<Experiment>('/experiments', b),
  cancelJob: (id: string) => post<Job>(`/jobs/${id}/cancel`),
  nasa: (b: Record<string, unknown>) => post<Job>('/datasets/nasa-power', b),
  createExport: (b: { source_type: string; source_id: string; format: string }) => post<ExportRecord>('/exports', b),
  resetSample: () => post<unknown>('/system/reset-sample'),
};
