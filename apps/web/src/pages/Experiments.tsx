import * as React from 'react';
import { useSearchParams } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Beaker, Play } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { mutations, useDefaults, useExperiment, useExperiments, useInvalidate, useModels, useSeasons } from '@/api/hooks';
import type { Experiment, ExperimentTableRow, Stat } from '@/api/types';
import { useWorkspace } from '@/app/workspace';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input, Select } from '@/components/ui/input';
import { Checkbox, Switch } from '@/components/ui/misc';
import { EmptyState, ErrorPanel, Field, LoadingBlock, NeedScenario, Notice, PageHeader, StatusBadge } from '@/components/common';
import { JobCard } from '@/components/JobCard';
import { ChartFrame, CHART, tooltipStyle } from '@/components/charts/ChartFrame';
import { cn, fmt, fmtSigned, relativeTime } from '@/lib/utils';

const METRICS: { key: string; label: string; unit: string; digits: number }[] = [
  { key: 'seasonal_irrigation_mm', label: 'Irrigation', unit: 'mm', digits: 1 },
  { key: 'yield_proxy_t_ha', label: 'Yield proxy', unit: 't/ha', digits: 3 },
  { key: 'aquacrop_yield_t_ha', label: 'AquaCrop yield', unit: 't/ha', digits: 3 },
  { key: 'irrigation_wp_proxy_kg_m3', label: 'Irrig. WP (proxy)', unit: 'kg/m³', digits: 2 },
  { key: 'cumulative_stress', label: 'Σ(1−Ks)', unit: '', digits: 2 },
  { key: 'stress_days', label: 'Stress days', unit: 'd', digits: 1 },
  { key: 'observation_count', label: 'Readings', unit: '', digits: 1 },
  { key: 'twin_rmse_mm', label: 'Twin RMSE', unit: 'mm', digits: 1 },
  { key: 'estimated_regret_mean', label: 'Est. regret', unit: '', digits: 4 },
  { key: 'objective_with_observation_cost', label: 'Objective', unit: '', digits: 2 },
];
const PAIRED = ['seasonal_irrigation_mm', 'yield_proxy_t_ha', 'cumulative_stress', 'objective_with_observation_cost', 'observation_count'];

function StatCell({ s, digits }: { s?: Stat; digits: number }) {
  if (!s || s.mean === null) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="tabular">
      {fmt(s.mean, digits)}
      {s.ci95 && <span className="block text-[11px] text-muted-foreground">[{fmt(s.ci95[0], digits)}, {fmt(s.ci95[1], digits)}]</span>}
    </span>
  );
}

function Results({ id }: { id: string }) {
  const exp = useExperiment(id);
  const [metric, setMetric] = React.useState('seasonal_irrigation_mm');
  if (exp.isLoading) return <LoadingBlock rows={3} />;
  if (exp.isError) return <ErrorPanel error={exp.error} retry={() => exp.refetch()} />;
  const e = exp.data as Experiment;
  if (e.status !== 'succeeded' || !e.summary) {
    return (
      <div className="flex flex-col gap-3">
        {e.job_id && <JobCard jobId={e.job_id} title={e.name} />}
        {e.status === 'failed' && <ErrorPanel title="Experiment failed" error={new Error(e.error ?? 'unknown error')} />}
      </div>
    );
  }
  const sm = e.summary;
  const m = METRICS.find((x) => x.key === metric)!;
  const chart = sm.table.map((t) => {
    const s = t[metric] as Stat | undefined;
    return { method: t.code, label: t.label, mean: s?.mean ?? null, err: s?.ci95 && s.mean !== null ? [s.mean - s.ci95[0], s.ci95[1] - s.mean] : [0, 0], n: s?.n ?? 0 };
  });
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>What did the data show?</CardTitle>
          <CardDescription>Generated deterministically from the paired statistics below. {sm.n_runs} runs, {sm.n_failed} failed, {sm.hard_constraint_violations} hard-constraint violations, {fmt(sm.runtime_seconds, 1)} s compute.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1 pl-5 text-sm">{sm.narrative.map((l) => <li key={l} className={l.startsWith('Negative') || l.startsWith('Caution') ? 'text-warning' : ''}>{l}</li>)}</ul>
        </CardContent>
      </Card>
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="metric" className="text-sm font-medium">Metric</label>
        <Select id="metric" value={metric} onChange={(ev) => setMetric(ev.target.value)} className="w-56">
          {METRICS.map((x) => <option key={x.key} value={x.key}>{x.label}{x.unit ? ` (${x.unit})` : ''}</option>)}
        </Select>
      </div>
      <ChartFrame
        name={`experiment-${id.slice(0, 8)}-${metric}`}
        title={`${m.label} by method — mean with bootstrap 95% CI`}
        description="Error bars are percentile bootstrap intervals of the mean over matched cells (absent when n < 5)."
        provenance={metric === 'aquacrop_yield_t_ha' ? ['aquacrop'] : metric === 'yield_proxy_t_ha' ? ['proxy'] : ['simulated']}
        rows={chart.map(({ err: _e, ...r }) => r)}
        columns={[{ key: 'method', label: 'Code' }, { key: 'label', label: 'Method' }, { key: 'mean', label: `Mean ${m.unit}` }, { key: 'n', label: 'n' }]}
      >
        <ResponsiveContainer>
          <BarChart data={chart} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
            <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="method" stroke={CHART.axis} fontSize={11} />
            <YAxis stroke={CHART.axis} fontSize={11} width={56} label={{ value: m.unit || m.label, angle: -90, position: 'insideLeft', fill: CHART.axis, fontSize: 11 }} />
            <Tooltip {...tooltipStyle} formatter={(v: number) => fmt(v, m.digits)} labelFormatter={(code) => chart.find((c) => c.method === code)?.label ?? String(code)} />
            <Bar dataKey="mean" name={m.label} fill={CHART.c1} isAnimationActive={false}>
              <ErrorBar dataKey="err" width={6} stroke={CHART.axis} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Card>
        <CardHeader><CardTitle>Method summary</CardTitle><CardDescription>Mean and [95% CI] per method across identical cells. Highlighted row = reference.</CardDescription></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr><th className="p-2">Method</th><th className="p-2">Runs</th>{METRICS.map((x) => <th key={x.key} className="p-2">{x.label}{x.unit ? ` (${x.unit})` : ''}</th>)}</tr>
            </thead>
            <tbody>
              {sm.table.map((t: ExperimentTableRow) => (
                <tr key={t.method} className={cn('border-t align-top', t.method === e.config.reference_method && 'bg-secondary')}>
                  <td className="p-2">
                    <Badge variant="outline" className="mr-1 font-mono">{t.code}</Badge>{t.label}
                    {t.role !== 'baseline' && <Badge variant={t.role === 'proposed' ? 'primary' : 'info'} className="ml-1">{t.role}</Badge>}
                  </td>
                  <td className="tabular p-2">{t.runs}{t.failed_runs ? <span className="text-destructive"> ({t.failed_runs} failed)</span> : null}</td>
                  {METRICS.map((x) => <td key={x.key} className="p-2"><StatCell s={t[x.key] as Stat} digits={x.digits} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Paired differences vs {e.config.reference_method}</CardTitle>
          <CardDescription>Method − reference on the same cell. “Better/worse” only when the bootstrap CI excludes zero; otherwise inconclusive.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr><th className="p-2">Method</th><th className="p-2">Metric</th><th className="p-2">Mean Δ</th><th className="p-2">95% CI</th><th className="p-2">n</th><th className="p-2">W/L/T</th><th className="p-2">Wilcoxon p</th><th className="p-2">Status</th></tr>
            </thead>
            <tbody>
              {Object.entries(sm.paired_vs_reference).flatMap(([method, comp]) =>
                PAIRED.map((key) => {
                  const c = comp[key];
                  if (!c || !c.n_pairs) return null;
                  return (
                    <tr key={`${method}-${key}`} className="border-t">
                      <td className="p-2">{method}</td>
                      <td className="p-2">{key}</td>
                      <td className="tabular p-2">{fmtSigned(c.mean_difference, 3)}</td>
                      <td className="tabular p-2">{c.ci95 ? `[${fmt(c.ci95[0], 3)}, ${fmt(c.ci95[1], 3)}]` : '—'}</td>
                      <td className="tabular p-2">{c.n_pairs}</td>
                      <td className="tabular p-2">{c.wins}/{c.losses}/{c.ties}</td>
                      <td className="tabular p-2">{c.wilcoxon_p == null ? '—' : c.wilcoxon_p.toPrecision(2)}</td>
                      <td className="p-2"><Badge variant={c.status.startsWith('better') ? 'success' : c.status.startsWith('worse') ? 'destructive' : 'outline'}>{c.status}</Badge></td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
          {Object.entries(sm.paired_vs_reference).map(([method, comp]) =>
            comp.water_savings_pct?.mean != null ? (
              <p key={method} className="mt-2 text-xs text-muted-foreground">{method}: simulated water savings vs reference {fmt(comp.water_savings_pct.mean as number, 1)} % (n {comp.water_savings_pct.n}).</p>
            ) : null,
          )}
        </CardContent>
      </Card>
      {sm.failures.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Failed runs</CardTitle><CardDescription>Shown, never hidden; excluded from statistics.</CardDescription></CardHeader>
          <CardContent><ul className="space-y-1 font-mono text-xs">{sm.failures.map((f, i) => <li key={i}>{f.method} · season {f.season_id} · seed {f.seed}: {f.error}</li>)}</ul></CardContent>
        </Card>
      )}
    </div>
  );
}

export default function Experiments() {
  const ws = useWorkspace();
  const defaults = useDefaults();
  const models = useModels(ws.scenarioId);
  const seasons = useSeasons(ws.scenarioId);
  const experiments = useExperiments(ws.scenarioId);
  const refresh = useInvalidate();
  const [params, setParams] = useSearchParams();
  const [methods, setMethods] = React.useState<string[]>(['fixed_schedule', 'soil_threshold', 'lookahead_carat']);
  const [reference, setReference] = React.useState('fixed_schedule');
  const [name, setName] = React.useState('Matched baseline comparison');
  const [split, setSplit] = React.useState<'test' | 'validation'>('test');
  const [seeds, setSeeds] = React.useState('1, 2, 3');
  const [budgets, setBudgets] = React.useState('10');
  const [noise, setNoise] = React.useState('0.02');
  const [mode, setMode] = React.useState('nominal');
  const [aquacrop, setAquacrop] = React.useState(false);
  const [modelId, setModelId] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const selected = params.get('id') ?? experiments.data?.[0]?.id ?? null;
  const needsModel = methods.some((m) => defaults.data?.methods.find((x) => x.key === m)?.needs_model);

  React.useEffect(() => {
    const m = models.data?.find((x) => x.selected) ?? models.data?.[0];
    if (!modelId && m) setModelId(m.id);
  }, [models.data, modelId]);

  if (!ws.loading && !ws.scenario) return <><PageHeader title="Experiment Benchmark" /><NeedScenario /></>;
  const list = (text: string) => text.split(',').map((x) => x.trim()).filter(Boolean).map(Number);
  const evalSeasons = seasons.data?.split?.[split] ?? [];
  const planned = methods.length * evalSeasons.length * list(seeds).length * list(budgets).length * list(noise).length;

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setError(null);
    if (!methods.includes(reference)) return setError('The reference method must be one of the selected methods.');
    if ([...list(seeds), ...list(budgets), ...list(noise)].some((x) => Number.isNaN(x))) return setError('Seeds, budgets and noise must be comma-separated numbers.');
    try {
      const exp = await mutations.experiment({
        scenario_id: ws.scenarioId, model_id: needsModel ? modelId || null : null, name, methods, reference_method: reference, split,
        seeds: list(seeds), observation_budgets: list(budgets), sensor_noise_m3m3: list(noise), sensor_mode: mode, aquacrop,
      });
      setParams({ id: exp.id });
      refresh('experiments', 'jobs');
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <>
      <PageHeader title="Experiment Benchmark" description="Matched comparisons: every method sees identical seasons, seeds, hidden farm draws, observation budgets and sensor noise. Results can show that CARAT does not help." />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[400px_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader><CardTitle>Design an experiment</CardTitle><CardDescription>{split === 'test' ? 'Held-out test' : 'Validation'} seasons: {evalSeasons.join(', ') || '—'}</CardDescription></CardHeader>
            <CardContent>
              <form onSubmit={submit} className="flex flex-col gap-3">
                <Field label="Name" htmlFor="x-name"><Input id="x-name" value={name} onChange={(e) => setName(e.target.value)} /></Field>
                <fieldset>
                  <legend className="mb-1.5 text-sm font-medium">Methods, baselines and ablations</legend>
                  <div className="flex max-h-72 flex-col gap-1.5 overflow-y-auto rounded-md border p-2">
                    {defaults.data?.methods.map((m) => (
                      <label key={m.key} className="flex items-start gap-2 text-sm">
                        <Checkbox checked={methods.includes(m.key)} onCheckedChange={(c) => setMethods((cur) => (c ? [...cur, m.key] : cur.filter((x) => x !== m.key)))} aria-label={m.label} className="mt-0.5" />
                        <span><Badge variant="outline" className="mr-1 font-mono">{m.code}</Badge>{m.label}{m.needs_model && <span className="text-xs text-muted-foreground"> · needs PPO</span>}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <Field label="Reference method (paired comparisons)" htmlFor="x-ref">
                  <Select id="x-ref" value={reference} onChange={(e) => setReference(e.target.value)}>{methods.map((m) => <option key={m} value={m}>{m}</option>)}</Select>
                </Field>
                {needsModel && (
                  <Field label="PPO model (same checkpoint for all PPO methods)" htmlFor="x-model" error={!models.data?.length ? 'Train a PPO model first' : undefined}>
                    <Select id="x-model" value={modelId} onChange={(e) => setModelId(e.target.value)}>
                      {models.data?.map((m) => <option key={m.id} value={m.id}>{m.preset} · seed {m.seed} · {m.actual_timesteps.toLocaleString()} steps{m.selected ? ' · selected' : ''}</option>)}
                    </Select>
                  </Field>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Split" htmlFor="x-split">
                    <Select id="x-split" value={split} onChange={(e) => setSplit(e.target.value as 'test' | 'validation')}><option value="test">test (held out)</option><option value="validation">validation (tuning)</option></Select>
                  </Field>
                  <Field label="Seeds" htmlFor="x-seeds"><Input id="x-seeds" value={seeds} onChange={(e) => setSeeds(e.target.value)} /></Field>
                  <Field label="Reading budgets" htmlFor="x-budgets" hint="e.g. 5, 10, 20, 40"><Input id="x-budgets" value={budgets} onChange={(e) => setBudgets(e.target.value)} /></Field>
                  <Field label="Sensor noise (m³/m³)" htmlFor="x-noise" hint="e.g. 0.01, 0.02, 0.04"><Input id="x-noise" value={noise} onChange={(e) => setNoise(e.target.value)} /></Field>
                  <Field label="Sensor scenario" htmlFor="x-mode">
                    <Select id="x-mode" value={mode} onChange={(e) => setMode(e.target.value)}>{defaults.data?.sensor_modes.map((s) => <option key={s} value={s}>{s}</option>)}</Select>
                  </Field>
                  <div className="flex items-end gap-2 pb-2 text-sm"><Switch id="x-aq" checked={aquacrop} onCheckedChange={setAquacrop} /><label htmlFor="x-aq">AquaCrop yield</label></div>
                </div>
                <Notice>Planned runs: <strong className="tabular">{planned}</strong> (methods × seasons × seeds × budgets × noise). Cap: 600 per experiment.</Notice>
                <Button type="submit" disabled={!methods.length || (needsModel && !modelId)}><Play aria-hidden />Queue experiment</Button>
                {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              </form>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Experiments</CardTitle></CardHeader>
            <CardContent>
              {!experiments.data?.length ? <p className="text-sm text-muted-foreground">None yet.</p> : (
                <ul className="flex flex-col gap-1.5">
                  {experiments.data.map((e) => (
                    <li key={e.id}>
                      <button type="button" onClick={() => setParams({ id: e.id })} aria-pressed={e.id === selected} className={cn('flex w-full items-center justify-between gap-2 rounded-md border p-2 text-left text-sm', e.id === selected && 'border-primary bg-secondary')}>
                        <span className="min-w-0"><span className="block truncate font-medium">{e.name}</span><span className="text-xs text-muted-foreground">{e.config.methods.length} methods · {e.n_runs ?? 0} runs · {relativeTime(e.created_at)}</span></span>
                        <StatusBadge status={e.status} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="min-w-0">
          {selected ? <Results id={selected} /> : <EmptyState icon={Beaker} title="No experiment yet" description="Queue a matched comparison. Non-PPO baselines and the CARAT planner work before any training." />}
        </div>
      </div>
    </>
  );
}
