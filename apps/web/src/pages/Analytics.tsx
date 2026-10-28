import * as React from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, ErrorBar, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts';
import { BarChart3 } from 'lucide-react';
import { useAnalytics, useExperiment, useExperiments, useRuns } from '@/api/hooks';
import type { Stat } from '@/api/types';
import { useWorkspace } from '@/app/workspace';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select } from '@/components/ui/input';
import { EmptyState, ErrorPanel, LoadingBlock, NeedScenario, Notice, PageHeader, Term } from '@/components/common';
import { ChartFrame, CHART, tooltipStyle } from '@/components/charts/ChartFrame';
import { fmt } from '@/lib/utils';

const PALETTE = [CHART.c1, CHART.c2, CHART.c3, CHART.c4, CHART.c5, 'hsl(160 40% 60%)', 'hsl(20 60% 55%)', 'hsl(250 40% 60%)', 'hsl(90 40% 45%)', 'hsl(330 45% 55%)', 'hsl(45 70% 45%)'];

export default function Analytics() {
  const ws = useWorkspace();
  const analytics = useAnalytics(ws.scenarioId);
  const runs = useRuns(ws.scenarioId);
  const experiments = useExperiments(ws.scenarioId);
  const done = (experiments.data ?? []).filter((e) => e.status === 'succeeded');
  const [expId, setExpId] = React.useState<string | null>(null);
  const [split, setSplit] = React.useState<'all' | 'train' | 'validation' | 'test'>('all');
  const exp = useExperiment(expId ?? done[0]?.id ?? null);
  if (!ws.loading && !ws.scenario) return <><PageHeader title="Insights & Analytics" /><NeedScenario /></>;
  if (analytics.isError) return <><PageHeader title="Insights & Analytics" /><ErrorPanel error={analytics.error} retry={() => analytics.refetch()} /></>;
  if (analytics.isLoading || runs.isLoading) return <><PageHeader title="Insights & Analytics" /><LoadingBlock rows={4} /></>;
  const filtered = (runs.data ?? []).filter((r) => split === 'all' || r.split === split);
  if (!runs.data?.length) {
    return (
      <>
        <PageHeader title="Insights & Analytics" />
        <EmptyState icon={BarChart3} title="No saved runs to analyse" description="Charts here are computed from saved run summaries only." action={<Button asChild><Link to="/simulation">Run a simulation</Link></Button>} />
      </>
    );
  }
  const methods = Array.from(new Set(filtered.map((r) => r.method_code)));
  const points = filtered.map((r) => ({
    code: r.method_code, label: r.method_label, irrigation: r.summary.seasonal_irrigation_mm, yield: r.summary.yield_proxy_t_ha,
    aquacrop: r.summary.aquacrop?.aquacrop_simulated_dry_yield_t_ha ?? null, stress: r.summary.cumulative_stress, readings: r.summary.observation_count,
    rmse: r.summary.twin_rmse_mm, season: r.season_id, seed: r.seed, split: r.split,
  }));
  const bars = analytics.data!.methods.map((m) => {
    const s = (k: string) => m[k] as Stat;
    return { code: m.code, label: m.label, runs: m.runs, irrigation: s('seasonal_irrigation_mm').mean, irrigation_sd: s('seasonal_irrigation_mm').std ?? 0,
      stress: s('cumulative_stress').mean, wp: s('irrigation_wp_proxy_kg_m3').mean, readings: s('observation_count').mean, rmse: s('twin_rmse_mm').mean };
  });
  const tableExp = exp.data?.summary;

  return (
    <>
      <PageHeader title="Insights & Analytics" description="Irrigation, simulated yield, water productivity, stress, observation efficiency and twin uncertainty — all computed from saved results." />
      <Notice className="mb-4">{analytics.data!.note}</Notice>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label htmlFor="slice" className="text-sm font-medium">Data slice</label>
        <Select id="slice" value={split} onChange={(e) => setSplit(e.target.value as typeof split)} className="w-48">
          <option value="all">All seasons</option><option value="train">Training seasons</option><option value="validation">Validation seasons</option><option value="test">Held-out test seasons</option>
        </Select>
        <span className="text-sm text-muted-foreground">{filtered.length} run(s)</span>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ChartFrame name="irrigation-vs-yield" title="Irrigation vs yield proxy (each run)" description="Trade-off between applied water and FAO-33 yield proxy." provenance={['simulated', 'proxy']}
          rows={points} columns={[{ key: 'code', label: 'Method' }, { key: 'season', label: 'Season' }, { key: 'seed', label: 'Seed' }, { key: 'irrigation', label: 'Irrigation (mm)' }, { key: 'yield', label: 'Yield proxy (t/ha)' }, { key: 'aquacrop', label: 'AquaCrop (t/ha)' }]} height={320}>
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 8, right: 12, bottom: 22, left: 4 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
              <XAxis dataKey="irrigation" type="number" name="Irrigation" unit=" mm" stroke={CHART.axis} fontSize={11} label={{ value: 'Seasonal irrigation (mm)', position: 'insideBottom', offset: -12, fill: CHART.axis, fontSize: 11 }} />
              <YAxis dataKey="yield" type="number" name="Yield proxy" unit=" t/ha" stroke={CHART.axis} fontSize={11} width={60} />
              <ZAxis range={[40, 40]} />
              <Tooltip {...tooltipStyle} cursor={{ strokeDasharray: '3 3' }} />
              <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
              {methods.map((code, i) => <Scatter key={code} name={code} data={points.filter((p) => p.code === code)} fill={PALETTE[i % PALETTE.length]} isAnimationActive={false} />)}
            </ScatterChart>
          </ResponsiveContainer>
        </ChartFrame>
        <ChartFrame name="irrigation-by-method" title="Mean seasonal irrigation by method (± SD)" description="Unmatched runs: seasons and seeds may differ between methods." provenance={['simulated']}
          rows={bars} columns={[{ key: 'code', label: 'Code' }, { key: 'runs', label: 'Runs' }, { key: 'irrigation', label: 'Irrigation (mm)' }, { key: 'irrigation_sd', label: 'SD (mm)' }]} height={320}>
          <ResponsiveContainer>
            <BarChart data={bars} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="code" stroke={CHART.axis} fontSize={11} />
              <YAxis stroke={CHART.axis} fontSize={11} width={52} label={{ value: 'mm', angle: -90, position: 'insideLeft', fill: CHART.axis, fontSize: 11 }} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="irrigation" name="Irrigation (mm)" fill={CHART.c1} isAnimationActive={false}><ErrorBar dataKey="irrigation_sd" width={5} stroke={CHART.axis} /></Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
        <ChartFrame name="observation-efficiency" title="Observation efficiency: readings vs twin RMSE" description="Does spending readings reduce estimation error? RMSE uses the hidden reference post-run." provenance={['simulated', 'truth']}
          rows={points} columns={[{ key: 'code', label: 'Method' }, { key: 'readings', label: 'Readings' }, { key: 'rmse', label: 'Twin RMSE (mm)' }, { key: 'stress', label: 'Σ(1−Ks)' }]} height={300}>
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 8, right: 12, bottom: 22, left: 4 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
              <XAxis dataKey="readings" type="number" name="Readings" stroke={CHART.axis} fontSize={11} label={{ value: 'Soil readings used', position: 'insideBottom', offset: -12, fill: CHART.axis, fontSize: 11 }} />
              <YAxis dataKey="rmse" type="number" name="Twin RMSE" unit=" mm" stroke={CHART.axis} fontSize={11} width={60} />
              <ZAxis range={[40, 40]} />
              <Tooltip {...tooltipStyle} />
              <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
              {methods.map((code, i) => <Scatter key={code} name={code} data={points.filter((p) => p.code === code)} fill={PALETTE[i % PALETTE.length]} isAnimationActive={false} />)}
            </ScatterChart>
          </ResponsiveContainer>
        </ChartFrame>
        <ChartFrame name="stress-by-method" title="Mean cumulative water stress by method" description="Σ(1 − Ks) over the season on the simulated farm (stress-day equivalents)." provenance={['simulated']}
          rows={bars} columns={[{ key: 'code', label: 'Code' }, { key: 'stress', label: 'Σ(1−Ks)' }, { key: 'wp', label: 'Irrigation WP proxy (kg/m³)' }, { key: 'readings', label: 'Mean readings' }]} height={300}>
          <ResponsiveContainer>
            <BarChart data={bars} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="code" stroke={CHART.axis} fontSize={11} />
              <YAxis stroke={CHART.axis} fontSize={11} width={52} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="stress" name="Σ(1−Ks)" fill={CHART.c3} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      </div>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Statistical comparison (matched experiment)</CardTitle>
          <CardDescription>Paired statistics live in experiments, where cells are matched. <Term id="wp">Water productivity</Term> and yields are simulated.</CardDescription>
        </CardHeader>
        <CardContent>
          {!done.length ? <p className="text-sm text-muted-foreground">No completed experiment for this scenario. <Link className="text-primary underline" to="/experiments">Design one</Link>.</p> : (
            <>
              <Select aria-label="Experiment" value={expId ?? done[0].id} onChange={(e) => setExpId(e.target.value)} className="mb-3 w-80">{done.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select>
              {exp.isLoading ? <LoadingBlock rows={2} /> : tableExp && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-xs text-muted-foreground"><tr><th className="p-2">Method</th><th className="p-2">n</th><th className="p-2">Irrigation (mm)</th><th className="p-2">Yield proxy (t/ha)</th><th className="p-2">Σ(1−Ks)</th><th className="p-2">Readings</th><th className="p-2">Twin RMSE (mm)</th></tr></thead>
                    <tbody>{tableExp.table.map((t) => {
                      const c = (k: string) => { const s = t[k] as Stat; return s?.mean == null ? '—' : `${fmt(s.mean, 2)}${s.ci95 ? ` [${fmt(s.ci95[0], 2)}, ${fmt(s.ci95[1], 2)}]` : ''}`; };
                      return <tr key={t.method} className="border-t"><td className="p-2">{t.code} {t.label}</td><td className="tabular p-2">{t.runs}</td><td className="tabular p-2">{c('seasonal_irrigation_mm')}</td><td className="tabular p-2">{c('yield_proxy_t_ha')}</td><td className="tabular p-2">{c('cumulative_stress')}</td><td className="tabular p-2">{c('observation_count')}</td><td className="tabular p-2">{c('twin_rmse_mm')}</td></tr>;
                    })}</tbody>
                  </table>
                  <ul className="mt-3 list-disc pl-5 text-sm">{tableExp.narrative.map((l) => <li key={l}>{l}</li>)}</ul>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </>
  );
}
