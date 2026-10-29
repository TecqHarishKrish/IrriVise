import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NAV } from '@/app/nav';
import { baseRoutes, mockApi, renderApp } from './helpers';

describe('routing and shell', () => {
  it.each(NAV.map((n) => [n.path, n.label]))('renders %s with heading "%s"', async (path, label) => {
    mockApi({ ...baseRoutes, '/config/defaults': { methods: [], actions_mm: [0, 5, 10, 15, 20], training_presets: {}, soils: {}, crops: {}, reward: {}, carat: {}, uncertainty: {}, risk: {}, sensor_modes: [], units: {}, policy_features: [] },
      '/system/diagnostics': new Response('{}', { status: 500 }), '/analytics/overview': { total_runs: 0, methods: [], note: '' }, '/scenarios/s1/seasons': { seasons: [], split: null, skipped: [] } });
    renderApp(path);
    expect(await screen.findByRole('heading', { level: 1, name: label })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
    const current = screen.getAllByRole('link', { name: new RegExp(label) }).find((a) => a.getAttribute('aria-current') === 'page');
    expect(current).toBeTruthy();
  });

  it('shows a not-found page for unknown routes', async () => {
    mockApi(baseRoutes);
    renderApp('/does-not-exist');
    expect(await screen.findByText('Page not found')).toBeInTheDocument();
  });

  it('shows an API-disconnected banner instead of fabricated data', async () => {
    mockApi({ ...baseRoutes, '/health': new Response('{"code":"internal_error","message":"boom","request_id":"x"}', { status: 500 }) });
    renderApp('/');
    await waitFor(() => expect(screen.getByText(/API disconnected/)).toBeInTheDocument(), { timeout: 4000 });
    expect(await screen.findByText('No simulation run yet')).toBeInTheDocument();
  });
});
