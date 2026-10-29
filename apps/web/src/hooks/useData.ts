import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import type { Project, Job, Run, Dataset, Day, ExperimentResult } from '../types';

// Re-export so pages can import DataReturn from here
export type { Project, Job, Run, Dataset, Day, ExperimentResult } from '../types';

export function useData() {
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => api<Project[]>('/api/v1/projects') });
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api<Job[]>('/api/v1/jobs'), refetchInterval: 2000 });
  const runs = useQuery({ queryKey: ['runs'], queryFn: () => api<Run[]>('/api/v1/simulations'), refetchInterval: 2500 });
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: () => api<Dataset[]>('/api/v1/datasets'), refetchInterval: 4000 });
  return { projects, jobs, runs, datasets };
}

export type DataReturn = ReturnType<typeof useData>;

export function useDaily(id?: string, evaluation = false) {
  return useQuery({
    queryKey: ['daily', id, evaluation],
    queryFn: () => api<Day[]>(`/api/v1/simulations/${id}/${evaluation ? 'evaluation' : 'daily'}`),
    enabled: !!id,
  });
}

export function useExperiments() {
  return useQuery({
    queryKey: ['experiments'],
    queryFn: () => api<ExperimentResult[]>('/api/v1/experiments'),
    refetchInterval: 3000,
  });
}
