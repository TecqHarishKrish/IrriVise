import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ApiError, errorMessage } from '@/api/client';
import { ErrorPanel, Kpi } from '@/components/common';
import { ChartFrame } from '@/components/charts/ChartFrame';
import { explainDecision } from '@/pages/CaratLab';
import { fmt, toCsv } from '@/lib/utils';
import type { DecisionTrace } from '@/api/types';

describe('formatting and errors', () => {
  it('never fabricates numbers for missing values', () => {
    expect(fmt(null)).toBe('—');
    expect(fmt(undefined)).toBe('—');
    expect(fmt(Number.NaN)).toBe('—');
    expect(fmt(1.234, 2)).toBe('1.23');
  });
  it('formats API validation details', () => {
    const e = new ApiError(422, 'validation_error', 'Request validation failed', [{ loc: ['body', 'name'], msg: 'too short' }]);
    expect(errorMessage(e)).toContain('name: too short');
  });
  it('escapes CSV values', () => {
    expect(toCsv([{ a: 'x,y', b: 1 }])).toBe('a,b\n"x,y",1');
  });
  it('renders error panel with retry', async () => {
    let retried = false;
    render(<ErrorPanel error={new Error('boom')} retry={() => (retried = true)} />);
    expect(screen.getByRole('alert')).toHaveTextContent('boom');
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(retried).toBe(true);
  });
  it('shows KPI with unit and provenance label', () => {
    render(<Kpi label="Irrigation" value="350" unit="mm" provenance="proxy" />);
    expect(screen.getByText('350')).toBeInTheDocument();
    expect(screen.getByText('mm')).toBeInTheDocument();
    expect(screen.getByText('Yield proxy')).toBeInTheDocument();
  });
});

describe('chart accessibility', () => {
  it('toggles to an accessible data table with the plotted rows', async () => {
    render(
      <ChartFrame name="t" title="Test chart" rows={[{ day: 1, v: 2.5 }, { day: 2, v: null }]} columns={[{ key: 'day', label: 'Day' }, { key: 'v', label: 'Value (mm)' }]}>
        <div>chart</div>
      </ChartFrame>,
    );
    expect(screen.getByRole('img', { name: 'Test chart' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /table/i }));
    const table = screen.getByRole('table', { name: 'Test chart' });
    expect(table).toHaveTextContent('Value (mm)');
    expect(table).toHaveTextContent('2.5');
    expect(table).toHaveTextContent('—');
  });
});

describe('CARAT explanation', () => {
  it('is built only from trace fields', () => {
    const trace = {
      day: 5, date: '2020-06-19', stage: 0, initial_action_mm: 10, observation_policy: 'carat', observe: false, observe_reason: 'net VOI -0.01 ≤ threshold',
      initial_belief: { mean_storage_mm: 80, std_storage_mm: 5, q10_storage_mm: 74, q90_storage_mm: 86, mean_theta: 0.2, depletion_fraction: 0.3, taw_mm: 60, raw_mm: 33, ks_estimate: 1, days_since_observation: 6, root_depth_m: 0.4 },
      forecast: { rain_mm: [], eto_mm: [], source: 'x', confidence: 'y' }, measurement: null, correction: null, corrected_belief: null, assessment_after: null,
      assessment_before: { day: 5, candidate_actions_mm: [0, 5], expected_values: [0, -0.05], prob_action_best: [1, 0], belief_action_mm: 0, policy_action_mm: 10, regret_before: 0, regret_policy_action: 0.1, expected_regret_after: 0, gross_voi: 0, observation_cost: 0.03, shadow_price: 0.02, net_voi: -0.05, observe_recommended: false, reason: '', states_agree: true, diagnostics: {} },
      proposed_mm: 10, applied_mm: 10, budgets: { water_remaining_before_mm: 300, water_remaining_after_mm: 290, observations_remaining: 10, observations_used: 0 },
      risk: { proposed_mm: 10, hard_projected_mm: 10, applied_mm: 10, constraint_status: 'ok', reasons: [], risk_flags: [], stress_probability: {}, predicted_stress_quantiles: {}, soft_layer_enabled: true },
    } as unknown as DecisionTrace;
    const lines = explainDecision(trace).join(' ');
    expect(lines).toContain('80.0 mm');
    expect(lines).toContain('preferred the same action');
    expect(lines).toContain('SKIP');
    expect(lines).toContain('applied 10 mm');
  });
});
