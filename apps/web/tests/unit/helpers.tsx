import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import { TooltipProvider } from '@/components/ui/tooltip';
import { WorkspaceProvider } from '@/app/workspace';
import { App } from '@/app/App';

type Handler = (url: string, init?: RequestInit) => unknown | Promise<unknown>;

/** Mock fetch with a route table: keys are URL prefixes (after /api/v1). Unmatched → 404 JSON error. */
export function mockApi(routes: Record<string, unknown | Handler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input).replace(/^\/api\/v1/, '');
    const key = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => url.startsWith(k));
    if (key === undefined) return new Response(JSON.stringify({ code: 'not_found', message: `No mock for ${url}`, request_id: 't' }), { status: 404 });
    const value = routes[key];
    const body = typeof value === 'function' ? await (value as Handler)(url, init) : value;
    if (body instanceof Response) return body;
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

export function renderApp(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <WorkspaceProvider><App /></WorkspaceProvider>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

export const health = { api: 'ok', database: 'ok', schema_revision: '0001', worker: { status: 'online' }, datasets: 1, sample_dataset: true, models: 0, runs: 0, active_jobs: 0, aquacrop: { available: true, detail: '3.1.0' }, mode: 'local' };
export const project = { id: 'p1', name: 'Sample field (synthetic)', description: '', crop: 'maize', is_sample: true, archived: false, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', scenario_count: 1 };
export const scenario = { id: 's1', project_id: 'p1', name: 'Kharif maize', latitude: 10.79, longitude: 78.7, crop_profile: 'maize', soil_profile: 'sandy_loam', planting_mmdd: '06-15', daily_max_mm: 20, seasonal_budget_mm: 350, observation_budget: 10, sensor_noise_m3m3: 0.02, sensor_mode: 'nominal', initial_fraction_mean: 0.7, dataset_id: 'd1', validation_status: 'valid', validation_messages: [], archived: false, advanced: {}, season_length_days: 140, scenario_sha256: 'abc', created_at: '', updated_at: '' };
export const baseRoutes = {
  '/health': health,
  '/projects?': [project],
  '/projects/p1/scenarios': [scenario],
  '/jobs': [],
  '/simulations': [],
  '/models': [],
  '/experiments': [],
  '/exports': [],
  '/datasets': [],
};
