import * as React from 'react';
import { useProjects, useScenarios } from '@/api/hooks';
import type { Project, Scenario } from '@/api/types';

interface Workspace {
  projectId: string | null;
  scenarioId: string | null;
  project: Project | undefined;
  scenario: Scenario | undefined;
  projects: Project[];
  scenarios: Scenario[];
  loading: boolean;
  select: (projectId: string | null, scenarioId?: string | null) => void;
  selectScenario: (scenarioId: string | null) => void;
}

const Ctx = React.createContext<Workspace | null>(null);
const read = (key: string) => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};
const write = (key: string, value: string | null) => {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    /* storage unavailable */
  }
};

/** Active project/scenario persisted per browser; validated against the API so stale ids are dropped. */
export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [projectId, setProjectId] = React.useState<string | null>(() => read('irrivise.project'));
  const [scenarioId, setScenarioId] = React.useState<string | null>(() => read('irrivise.scenario'));
  const projects = useProjects();
  const scenarios = useScenarios(projectId);

  React.useEffect(() => {
    if (!projects.data) return;
    if (projectId && !projects.data.some((p) => p.id === projectId)) {
      setProjectId(projects.data[0]?.id ?? null);
      setScenarioId(null);
    } else if (!projectId && projects.data.length) {
      setProjectId(projects.data[0].id);
    }
  }, [projects.data, projectId]);

  React.useEffect(() => {
    if (!scenarios.data) return;
    if (!scenarioId || !scenarios.data.some((s) => s.id === scenarioId)) setScenarioId(scenarios.data[0]?.id ?? null);
  }, [scenarios.data, scenarioId]);

  React.useEffect(() => write('irrivise.project', projectId), [projectId]);
  React.useEffect(() => write('irrivise.scenario', scenarioId), [scenarioId]);

  const value: Workspace = {
    projectId,
    scenarioId,
    project: projects.data?.find((p) => p.id === projectId),
    scenario: scenarios.data?.find((s) => s.id === scenarioId),
    projects: projects.data ?? [],
    scenarios: scenarios.data ?? [],
    loading: projects.isLoading || (!!projectId && scenarios.isLoading),
    select: (p, s = null) => {
      setProjectId(p);
      setScenarioId(s);
    },
    selectScenario: setScenarioId,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspace() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error('useWorkspace outside provider');
  return ctx;
}
