import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { baseRoutes, mockApi, project, renderApp } from './helpers';

describe('project form', () => {
  it('validates inline and posts a valid project', async () => {
    const created: unknown[] = [];
    mockApi({
      ...baseRoutes,
      '/projects': (_url: string, init?: RequestInit) => {
        if (init?.method === 'POST') { created.push(JSON.parse(String(init.body))); return { ...project, id: 'p2', name: 'New field' }; }
        return [project];
      },
      '/config/defaults': { soils: {}, methods: [] },
    });
    renderApp('/projects?new=1');
    const name = await screen.findByLabelText('Project name');
    await userEvent.clear(name);
    await userEvent.type(name, 'x');
    await userEvent.click(screen.getByRole('button', { name: 'Create project' }));
    expect(await screen.findByText('At least 2 characters')).toBeInTheDocument();
    expect(created).toHaveLength(0);
    await userEvent.type(name, 'yz field');
    await userEvent.click(screen.getByRole('button', { name: 'Create project' }));
    await waitFor(() => expect(created).toHaveLength(1));
    expect(created[0]).toMatchObject({ name: 'xyz field' });
  });
});

describe('training lab without models', () => {
  it('shows an honest empty state rather than fake curves', async () => {
    mockApi({ ...baseRoutes, '/config/defaults': { training_presets: {}, reward: {}, actions_mm: [], methods: [] }, '/scenarios/s1/seasons': { seasons: [], split: { train: ['2004'], validation: [], test: [], rule: 'r' }, skipped: [] } });
    renderApp('/training');
    expect(await screen.findByText('No training run yet')).toBeInTheDocument();
    expect(await screen.findByText(/No trained models/)).toBeInTheDocument();
  });
});
