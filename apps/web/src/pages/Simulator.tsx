import * as React from 'react';
import { useSearchParams } from 'react-router-dom';
import type { ColumnDef } from '@tanstack/react-table';
import { Droplets, Play } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { mutations, useDaily, useDefaults, useInvalidate, useJob, useModels, useRun, useSeasons } from '@/api/hooks';
import type { DailyRow } from '@/api/types';
import { useWorkspace } from '@/app/workspace';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input, Select } from '@/components/ui/input';
import { Switch } from '@/components/ui/misc';
import { EmptyState, ErrorPanel, Field, Kpi, LoadingBlock, NeedScenario, Notice, PageHeader, Term } from '@/components/common';
import { DataTable } from '@/components/DataTable';
import { DayStepper } from '@/components/DayStepper';
import { JobCard } from '@/components/JobCard';
import { RunPicker } from '@/components/RunPicker';
import { SoilWaterChart, StressChart, WaterChart } from '@/components/charts/SeasonCharts';
import { fmt, STAGES } from '@/lib/utils';

const columns: ColumnDef<DailyRow, unknown>[] = [
  { accessorKey: 'day', header: 'Day' },
  { accessorKey: 'date', header: 'Date' },
  { accessorKey: 'rain_mm', header: 'Rain (mm)' },
  { accessorKey: 'belief_mean_mm', header: 'Twin mean (mm)', cell: (c) => fmt(c.getValue() as number, 1) },
  { accessorKey: 'belief_std_mm', header: 'Twin σ (mm)', cell: (c) => fmt(c.getValue() as number, 1) },
  { accessorKey: 'initial_action_mm', header: 'Initial (mm)' },
  { accessorKey: 'observed', header: 'Reading', cell: (c) => (c.getValue() ? 'yes' : '') },
  { accessorKey: 'proposed_mm', header: 'Proposed (mm)' },
  { accessorKey: 'applied_mm', header: 'Applied (mm)' },
  { accessorKey: 'constraint_status', header: 'Constraint' },
  { accessorKey: 'risk_flags', header: 'Risk flags' },
  { accessorKey: 'remaining_water_mm', header: 'Water left (mm)', cell: (c) => fmt(c.getValue() as number, 0) },
];

export default function Simulator() {
  const ws = useWorkspace();
  const [params, setParams] = useSearchParams();
  const defaults = useDefaults();
  const seasons = useSeasons(ws.scenarioId);
  const models = useModels(ws.scenarioId);
  const refresh = useInvalidate();
  const [method, setMethod] = React.useState(params.get('start') ?? 'fixed_schedule');
  const [modelId, setModelId] = React.useState<string>('');
  const [seasonId, setSeasonId] = React.useState<string>('');
  const [seed, setSeed] = React.useState(42);
  const [aquacrop, setAquacrop] = React.useState(true);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const runId = params.get('run');
  const run = useRun(runId);
  const daily = useDaily(runId);
  const [day, setDay] = React.useState(1);
  const spec = defaults.data?.methods.find((m) => m.key === method);
  const autoStarted = React.useRef(false);

  React.useEffect(() => {
    if (!seasonId && seasons.data?.split) setSeasonId(seasons.data.split.test[0] ?? seasons.data.seasons.at(-1)?.season_id ?? '');
  }, [seasons.data, seasonId]);
  React.useEffect(() => {
    const ready = models.data?.find((m) => m.selected) ?? models.data?.[0];
    if (!modelId && ready) setModelId(ready.id);
  }, [models.data, modelId]);

  const start = React.useCallback(async () => {
    if (!ws.scenarioId) return;
    setError(null);
    try {
      const job = await mutations.simulate({ scenario_id: ws.scenarioId, method, model_id: spec?.needs_model ? modelId || null : null, season_id: seasonId || null, seed, aquacrop });
      setJobId(job.id);
      refresh('jobs');
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [ws.scenarioId, method, spec, modelId, seasonId, seed, aquacrop, refresh]);

  React.useEffect(() => {
    if (params.get('start') && ws.scenario?.dataset_id && seasonId && !autoStarted.current) {
      autoStarted.current = true;
      start();
      setParams({});
    }
  }, [params, ws.scenario, seasonId, start, setParams]);

  if (!ws.loading && !ws.scenario) return <><PageHeader title="Irrigation Simulator" /><NeedScenario /></>;
  const rows = daily.data?.rows ?? [];
  const current = rows[day - 1];
  const s = run.data?.summary;

  return (
    <>
      <PageHeader title="Irrigation Simulator" description="Configure a controller, run a season in the worker, then step through the saved daily record. All charts read the stored trace." />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader><CardTitle>Run configuration</CardTitle><CardDescription>{ws.scenario?.name}</CardDescription></CardHeader>
            <CardContent>
              <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); start(); }}>
                <Field label="Controller / method" htmlFor="sim-method" hint={spec?.note}>
                  <Select id="sim-method" value={method} onChange={(e) => setMethod(e.target.value)}>
                    {defaults.data?.methods.map((m) => <option key={m.key} value={m.key}>{m.code} · {m.label}</option>)}
                  </Select>
                </Field>
                {spec?.needs_model && (
                  <Field label="PPO model" htmlFor="sim-model" error={!models.data?.length ? 'No trained model yet — train one in the Model Training Lab or choose a non-PPO method.' : undefined}>
                    <Select id="sim-model" value={modelId} onChange={(e) => setModelId(e.target.value)} disabled={!models.data?.length}>
                      {models.data?.map((m) => <option key={m.id} value={m.id}>{m.preset} · seed {m.seed} · {m.actual_timesteps.toLocaleString()} steps{m.selected ? ' · selected' : ''}</option>)}
                    </Select>
                  </Field>
                )}
                <Field label="Season" htmlFor="sim-season" hint={seasons.data?.split?.rule}>
                  <Select id="sim-season" value={seasonId} onChange={(e) => setSeasonId(e.target.value)}>
                    {seasons.data?.seasons.map((x) => <option key={x.season_id} value={x.season_id}>{x.season_id} · {x.split} · {fmt(x.rain_mm, 0)} mm rain</option>)}
                  </Select>
                </Field>
                <Field label="Seed" htmlFor="sim-seed" hint="Fixes hidden farm parameters, gauge and sensor noise."><Input id="sim-seed" type="number" min={0} value={seed} onChange={(e) => setSeed(Math.max(0, Number(e.target.value)))} /></Field>
                <div className="flex items-center gap-2 text-sm"><Switch id="sim-aq" checked={aquacrop} onCheckedChange={setAquacrop} /><label htmlFor="sim-aq">Evaluate schedule in <Term id="aquacrop">AquaCrop</Term></label></div>
                {seasons.data?.split && seasons.data.split.train.includes(seasonId) && <Notice tone="warning">This is a training season. Use test seasons for held-out evaluation.</Notice>}
                <Button type="submit" disabled={!ws.scenario?.dataset_id || (spec?.needs_model && !modelId)}><Play aria-hidden />Queue simulation</Button>
                {!ws.scenario?.dataset_id && <p className="text-xs text-destructive">Attach a dataset to the scenario first.</p>}
                {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              </form>
            </CardContent>
          </Card>
          {jobId && <JobCard jobId={jobId} title="Simulation" />}
          {jobId && <JobResultLink jobId={jobId} onOpen={(id) => setParams({ run: id })} />}
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Card className="p-4"><RunPicker scenarioId={ws.scenarioId} value={runId} onChange={(id) => setParams({ run: id })} /></Card>
          {!runId ? <EmptyState icon={Droplets} title="Select or run a simulation" description="Saved daily records, charts and step-through replay appear here." /> :
            run.isError ? <ErrorPanel error={run.error} retry={() => run.refetch()} /> : !s || daily.isLoading ? <LoadingBlock rows={4} /> : (
              <>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge variant="outline" className="font-mono">{run.data!.method_code}</Badge><span className="font-medium">{run.data!.method_label}</span>
                  <span className="text-muted-foreground">season {run.data!.season_id} ({run.data!.split}) · seed {run.data!.seed}</span>
                </div>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <Kpi label="Irrigation" value={fmt(s.seasonal_irrigation_mm, 0)} unit="mm" provenance="simulated" hint={`${s.irrigation_events} events`} />
                  <Kpi label={<Term id="proxy">Yield proxy</Term>} value={fmt(s.yield_proxy_t_ha, 2)} unit="t/ha" provenance="proxy" />
                  <Kpi label={<Term id="aquacrop">AquaCrop yield</Term>} value={fmt(s.aquacrop?.aquacrop_simulated_dry_yield_t_ha, 2)} unit="t/ha" provenance="aquacrop" hint={s.aquacrop?.error ?? (s.aquacrop ? undefined : 'not evaluated')} />
                  <Kpi label={<Term id="wp">Irrigation WP</Term>} value={fmt(s.irrigation_wp_proxy_kg_m3, 2)} unit="kg/m³" provenance="proxy" />
                  <Kpi label="Soil readings" value={String(s.observation_count)} unit={`of ${s.observation_count + s.observations_remaining}`} provenance="simulated" />
                  <Kpi label="Stress days" value={String(s.stress_days)} unit="days" provenance="simulated" hint={`Σ(1−Ks) ${fmt(s.cumulative_stress, 1)}`} />
                  <Kpi label="Constraint violations" value={String(s.max_daily_violations + s.season_budget_violations)} provenance="simulated" hint="must be 0" />
                  <Kpi label="Runtime" value={fmt(s.runtime_seconds, 2)} unit="s" provenance="config" />
                </div>
                <WaterChart rows={rows} name={`water-${runId.slice(0, 8)}`} />
                <SoilWaterChart rows={rows} name={`soil-${runId.slice(0, 8)}`} />
                <StressChart rows={rows} name={`stress-${runId.slice(0, 8)}`} />
                {current && (
                  <Card>
                    <CardHeader><CardTitle>Step through saved daily records</CardTitle><CardDescription>Replay of stored decisions — not a re-simulation.</CardDescription></CardHeader>
                    <CardContent className="flex flex-col gap-4">
                      <DayStepper day={day} max={rows.length} onChange={setDay} />
                      <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
                        <div><dt className="text-xs text-muted-foreground">Date · stage</dt><dd>{current.date} · {STAGES[current.stage]}</dd></div>
                        <div><dt className="text-xs text-muted-foreground">Rain (realized / observed)</dt><dd className="tabular">{fmt(current.rain_mm)} / {fmt(current.rain_observed_mm)} mm</dd></div>
                        <div><dt className="text-xs text-muted-foreground">Forecast rain · ET₀</dt><dd className="tabular">{fmt(current.forecast_rain_mm)} · {fmt(current.forecast_eto_mm)} mm</dd></div>
                        <div><dt className="text-xs text-muted-foreground">Twin estimate</dt><dd className="tabular">{fmt(current.belief_mean_mm)} ± {fmt(current.belief_std_mm)} mm</dd></div>
                        <div><dt className="text-xs text-muted-foreground">Initial → proposed → applied</dt><dd className="tabular">{current.initial_action_mm} → {current.proposed_mm} → <strong>{current.applied_mm} mm</strong></dd></div>
                        <div><dt className="text-xs text-muted-foreground">Soil reading</dt><dd>{current.observation_attempted ? `${current.measurement_status}${current.measurement_theta != null ? ` · θ ${current.measurement_theta}` : ''}` : 'none'}</dd></div>
                        <div><dt className="text-xs text-muted-foreground">Constraint / risk</dt><dd>{current.constraint_status}{current.risk_flags ? ` · ${current.risk_flags}` : ''}</dd></div>
                        <div><dt className="text-xs text-muted-foreground">Budgets left</dt><dd className="tabular">{fmt(current.remaining_water_mm, 0)} mm · {current.remaining_observations} readings</dd></div>
                      </dl>
                    </CardContent>
                  </Card>
                )}
                <Card><CardHeader><CardTitle>Daily records</CardTitle></CardHeader><CardContent><DataTable data={rows} columns={columns} pageSize={14} caption="Saved daily simulation records" exportName={`daily-${runId.slice(0, 8)}`} onRowClick={(r) => setDay(r.day)} rowLabel={(r) => `Show day ${r.day}`} /></CardContent></Card>
              </>
            )}
        </div>
      </div>
    </>
  );
}

function JobResultLink({ jobId, onOpen }: { jobId: string; onOpen: (runId: string) => void }) {
  const opened = React.useRef(false);
  const { data } = useJob(jobId);
  React.useEffect(() => {
    const id = data?.result?.run_id as string | undefined;
    if (data?.status === 'succeeded' && id && !opened.current) {
      opened.current = true;
      onOpen(id);
    }
  }, [data, onOpen]);
  return null;
}
