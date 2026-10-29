import { NavLink } from 'react-router-dom';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Droplets, FlaskConical, Plus, Database, Play } from 'lucide-react';
import { Panel, Stat, RunList, ChartLegendLabel } from '../components/ui';
import { CHART_COLORS, tooltipStyle } from '../chartConfig';
import type { DataReturn, Run } from '../types';

export function Home({ data, latest }: { data: DataReturn; latest?: Run }) {
  const runs = data.runs.data || [];
  const sparkData = runs.slice(0, 12).reverse().map((r: Run, i: number) => ({
    x: i,
    irr: r.summary.seasonal_irrigation_mm,
  }));

  return (
    <>
      <div className="intro">
        <div>
          <span className="eyebrow light">SEASON OVERVIEW</span>
          <h2>Decisions shaped by evidence.</h2>
          <p>
            Explore a simulated field, compare practical irrigation policies, and inspect
            how uncertainty affects each recommendation.
          </p>
          <div style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
            <NavLink className="button white" to="/simulation">
              <Play size={15} /> Start a simulation
            </NavLink>
            <NavLink
              className="button"
              to="/carat"
              style={{ background: 'transparent', borderColor: '#ffffff55', color: '#d8f3e7' }}
            >
              <FlaskConical size={15} /> Inspect CARAT
            </NavLink>
          </div>
        </div>
        <div className="intro-art" aria-hidden="true">
          {sparkData.length > 1 ? (
            <ResponsiveContainer width="100%" height={120}>
              <AreaChart data={sparkData} margin={{ top: 5, right: 5, bottom: 0, left: 5 }}>
                <defs>
                  <linearGradient id="heroGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#76efcb" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="#76efcb" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Area type="monotone" dataKey="irr" stroke="#a5f0d8" fill="url(#heroGrad)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <>
              <span className="orb orb1" /><span className="orb orb2" /><span className="orb orb3" />
              <Droplets size={64} />
            </>
          )}
        </div>
      </div>

      <div className="stats">
        <Stat label="Projects" value={String(data.projects.data?.length ?? '—')} sub="Saved locally" />
        <Stat
          label="Completed runs"
          value={String(runs.length)}
          sub={`${data.datasets.data?.length ?? 0} weather datasets`}
        />
        <Stat
          label="Latest irrigation"
          value={latest ? `${latest.summary.seasonal_irrigation_mm.toFixed(0)} mm` : '—'}
          sub="Seasonal total"
        />
        <Stat
          label="AquaCrop dry yield"
          value={
            latest?.summary.aquacrop
              ? `${latest.summary.aquacrop.aquacrop_simulated_dry_yield_t_ha.toFixed(2)} t/ha`
              : '—'
          }
          sub={`AquaCrop-simulated · ${latest?.summary.dataset_source || 'n/a'}`}
          accent
        />
      </div>

      <div className="grid two">
        <Panel
          title="Recent simulation runs"
          action={<NavLink className="text-link" to="/simulation"><Plus size={13} />New run</NavLink>}
        >
          <RunList runs={runs} />
        </Panel>

        <Panel title="Get started">
          <ol className="steps">
            <li>Create a field project and season scenario.</li>
            <li>Run an offline season with the synthetic weather fixture.</li>
            <li>Inspect the digital twin and CARAT decision trace.</li>
            <li>Train a quick PPO policy and compare against baselines.</li>
            <li>Export the reproducible run manifest and daily data.</li>
          </ol>
          <NavLink className="text-link" to="/projects">Open Projects &amp; Fields →</NavLink>
          {runs.length >= 2 && (
            <div style={{ marginTop: 12 }}>
              <NavLink className="text-link" to="/experiments">
                <Database size={13} />Run a matched benchmark →
              </NavLink>
            </div>
          )}
        </Panel>
      </div>

      {runs.length >= 2 && (
        <Panel title="Run comparison — seasonal irrigation vs stress proxy">
          <p className="muted">
            All completed runs shown together. Runs may use different scenarios and weather;
            this is not a matched research benchmark.
          </p>
          <div style={{ display: 'flex', gap: 16, marginBottom: 8, flexWrap: 'wrap' }}>
            <ChartLegendLabel color={CHART_COLORS.irrigation} label="Irrigation (mm)" />
            <ChartLegendLabel color={CHART_COLORS.stress} label="Stress proxy" />
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={runs.slice(0, 12).reverse().map((r: Run) => ({
                name: r.controller.slice(0, 10),
                irrigation: +r.summary.seasonal_irrigation_mm.toFixed(1),
                stress: +r.summary.cumulative_stress_proxy.toFixed(2),
              }))}
              margin={{ top: 10, right: 20, bottom: 5, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--muted)' }} />
              <YAxis yAxisId="left" tick={{ fontSize: 10, fill: 'var(--muted)' }} unit=" mm" />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: 'var(--muted)' }} />
              <Tooltip {...tooltipStyle} />
              <Bar yAxisId="left" dataKey="irrigation" fill={CHART_COLORS.irrigation} radius={[4,4,0,0]} name="Irrigation (mm)" />
              <Bar yAxisId="right" dataKey="stress" fill={CHART_COLORS.stress} radius={[4,4,0,0]} name="Stress proxy" />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      )}
    </>
  );
}
