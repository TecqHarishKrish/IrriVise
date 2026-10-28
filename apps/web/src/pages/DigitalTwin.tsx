import * as React from 'react';
import { useSearchParams } from 'react-router-dom';
import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Activity, ShieldAlert } from 'lucide-react';
import { useDaily, useEvaluation, useRun, useRuns } from '@/api/hooks';
import type { DailyRow, TruthRow } from '@/api/types';
import { useWorkspace } from '@/app/workspace';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/misc';
import { EmptyState, ErrorPanel, Kpi, LoadingBlock, NeedScenario, Notice, PageHeader, ProvenanceBadge, Term } from '@/components/common';
import { DayStepper } from '@/components/DayStepper';
import { RunPicker } from '@/components/RunPicker';
import { ChartFrame, CHART, tooltipStyle } from '@/components/charts/ChartFrame';
import { SoilWaterChart, StressChart } from '@/components/charts/SeasonCharts';
import { fmt, STAGES } from '@/lib/utils';

/** Root-zone "reservoir": wilting point at the bottom, field capacity line, plausible band and mean. */
function Reservoir({ row, truth }: { row: DailyRow; truth?: TruthRow | null }) {
  const fc = row.belief_mean_mm + row.est_depletion_fraction * row.taw_mm; // ≈ storage at field capacity
  const wp = fc - row.taw_mm;
  const top = fc + 0.6 * row.taw_mm;
  const y = (v: number) => 220 - ((v - wp) / (top - wp)) * 200;
  const mean = y(row.belief_mean_mm);
  return (
    <svg viewBox="0 0 220 240" className="h-64 w-full max-w-[260px]" role="img" aria-label={`Root zone on day ${row.day}: estimated ${row.belief_mean_mm.toFixed(0)} mm, plausible ${row.belief_q10_mm.toFixed(0)}–${row.belief_q90_mm.toFixed(0)} mm, field capacity about ${fc.toFixed(0)} mm, stress onset at ${(fc - row.raw_mm).toFixed(0)} mm`}>
      <rect x="50" y="20" width="110" height="200" rx="6" fill="hsl(var(--muted))" stroke="hsl(var(--border))" />
      <rect x="50" y={mean} width="110" height={Math.max(0, 220 - mean)} rx="4" fill="hsl(var(--chart-2) / 0.35)" />
      <rect x="50" y={y(row.belief_q90_mm)} width="110" height={Math.max(2, y(row.belief_q10_mm) - y(row.belief_q90_mm))} fill="hsl(var(--chart-1) / 0.25)" />
      <line x1="44" x2="166" y1={mean} y2={mean} stroke="hsl(var(--chart-1))" strokeWidth="3" />
      <line x1="44" x2="166" y1={y(fc)} y2={y(fc)} stroke="hsl(var(--foreground))" strokeDasharray="4 3" />
      <line x1="44" x2="166" y1={y(fc - row.raw_mm)} y2={y(fc - row.raw_mm)} stroke="hsl(var(--chart-3))" strokeDasharray="4 3" />
      {truth && <line x1="44" x2="166" y1={y(truth.true_storage_mm)} y2={y(truth.true_storage_mm)} stroke="hsl(var(--destructive))" strokeWidth="2" strokeDasharray="2 2" />}
      <text x="170" y={y(fc) + 4} fontSize="10" fill="hsl(var(--foreground))">FC</text>
      <text x="170" y={y(fc - row.raw_mm) + 4} fontSize="10" fill="hsl(var(--chart-3))">RAW</text>
      <text x="170" y={mean + 4} fontSize="10" fill="hsl(var(--chart-1))">est.</text>
      <text x="4" y="224" fontSize="10" fill="hsl(var(--muted-foreground))">WP</text>
      {truth && <text x="170" y={y(truth.true_storage_mm) + 14} fontSize="10" fill="hsl(var(--destructive))">ref.</text>}
    </svg>
  );
}

function CropTimeline({ rows, day }: { rows: DailyRow[]; day: number }) {
  const bounds = STAGES.map((_, i) => rows.filter((r) => r.stage === i).length);
  return (
    <div>
      <div className="flex h-8 w-full overflow-hidden rounded-md border text-[11px]" role="img" aria-label={`Crop stages: ${STAGES.map((s, i) => `${s} ${bounds[i]} days`).join(', ')}`}>
        {bounds.map((n, i) => (
          <div key={i} className="flex items-center justify-center border-r last:border-0" style={{ width: `${(100 * n) / rows.length}%`, background: `hsl(var(--chart-1) / ${0.12 + i * 0.12})` }}>
            <span className="truncate px-1">{STAGES[i]}</span>
          </div>
        ))}
      </div>
      <div className="relative mt-1 h-3"><div className="absolute top-0 h-3 w-0.5 bg-foreground" style={{ left: `${(100 * (day - 0.5)) / rows.length}%` }} aria-hidden /></div>
    </div>
  );
}

export default function DigitalTwin() {
  const ws = useWorkspace();
  const [params, setParams] = useSearchParams();
  const runs = useRuns(ws.scenarioId);
  const runId = params.get('run') ?? runs.data?.[0]?.id ?? null;
  const run = useRun(runId);
  const daily = useDaily(runId);
  const [evaluationMode, setEvaluationMode] = React.useState(false);
  const evaluation = useEvaluation(runId, evaluationMode);
  const [day, setDay] = React.useState(1);
  if (!ws.loading && !ws.scenario) return <><PageHeader title="Digital Twin Studio" /><NeedScenario /></>;
  const rows = daily.data?.rows ?? [];
  const truth = evaluationMode ? evaluation.data?.rows ?? null : null;
  const row = rows[Math.min(day, rows.length) - 1];
  const uncertainty = rows.map((r) => ({ day: r.day, std: r.belief_std_mm, theta: r.belief_theta, reading: r.observed ? r.belief_std_mm : null }));

  return (
    <>
      <PageHeader title="Digital Twin Studio" description={<>The <Term id="twin">estimated digital twin</Term>: plausible soil-water states, uncertainty growth between readings and corrections after them.</>} />
      <Card className="mb-4 flex flex-wrap items-end justify-between gap-4 p-4">
        <RunPicker scenarioId={ws.scenarioId} value={runId} onChange={(id) => setParams({ run: id })} />
        <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive-soft px-3 py-2 text-sm">
          <ShieldAlert className="size-4 text-destructive" aria-hidden />
          <Switch id="eval-mode" checked={evaluationMode} onCheckedChange={setEvaluationMode} />
          <label htmlFor="eval-mode">Post-run evaluation mode (reveal simulated reference)</label>
        </div>
      </Card>
      {evaluationMode && (
        <Notice tone="warning" className="mb-4"><strong>Evaluation only.</strong> The hidden reference farm is shown to measure twin error after the season. It was never available to the policy, CARAT or the risk manager. {evaluation.data?.label}</Notice>
      )}
      {!runId ? <EmptyState icon={Activity} title="No run to inspect" description="Run a simulation first; the twin trace is saved with every run." action={<Button asChild><a href="/simulation">Open simulator</a></Button>} /> :
        daily.isError ? <ErrorPanel error={daily.error} retry={() => daily.refetch()} /> : daily.isLoading || !row ? <LoadingBlock rows={4} /> : (
          <div className="flex min-w-0 flex-col gap-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Kpi label="Twin RMSE" value={evaluationMode ? fmt(run.data?.summary.twin_rmse_mm, 1) : '—'} unit="mm" provenance="truth" hint={evaluationMode ? `${fmt(run.data?.summary.twin_rmse_m3m3, 4)} m³/m³` : 'enable evaluation mode'} />
              <Kpi label="Twin bias" value={evaluationMode ? fmt(run.data?.summary.twin_bias_mm, 1) : '—'} unit="mm" provenance="truth" />
              <Kpi label="Readings used" value={String(run.data?.summary.observation_count ?? '—')} provenance="simulated" />
              <Kpi label={<Term id="uncertainty">Mean σ</Term>} value={fmt(rows.reduce((a, r) => a + r.belief_std_mm, 0) / rows.length, 1)} unit="mm" provenance="estimated" />
            </div>
            <Card>
              <CardHeader><CardTitle>Root-zone state on a chosen day</CardTitle><CardDescription>Reservoir view of the belief at the start of the day (before any reading).</CardDescription></CardHeader>
              <CardContent className="flex flex-col gap-4">
                <DayStepper day={day} max={rows.length} onChange={setDay} />
                <CropTimeline rows={rows} day={day} />
                <div className="grid items-center gap-4 md:grid-cols-[280px_1fr]">
                  <Reservoir row={row} truth={truth?.[day - 1]} />
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    <div><dt className="text-xs text-muted-foreground">Date · stage</dt><dd>{row.date} · {STAGES[row.stage]} (Kc {row.kc})</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Root depth</dt><dd className="tabular">{fmt(row.root_depth_m, 2)} m</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Estimated storage</dt><dd className="tabular">{fmt(row.belief_mean_mm)} mm (θ {fmt(row.belief_theta, 3)} m³/m³)</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Plausible range (10–90 %)</dt><dd className="tabular">{fmt(row.belief_q10_mm)}–{fmt(row.belief_q90_mm)} mm</dd></div>
                    <div><dt className="text-xs text-muted-foreground"><Term id="taw">TAW / RAW</Term></dt><dd className="tabular">{fmt(row.taw_mm)} / {fmt(row.raw_mm)} mm</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Est. depletion · Ks</dt><dd className="tabular">{fmt(100 * row.est_depletion_fraction, 0)} % TAW · {fmt(row.est_ks, 2)}</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Reading today</dt><dd>{row.observation_attempted ? `${row.measurement_status}${row.corrected_mean_mm != null ? ` → corrected to ${fmt(row.corrected_mean_mm)} mm` : ''}` : 'none'}</dd></div>
                    {truth?.[day - 1] && <div><dt className="text-xs text-destructive">Reference (end of day, eval.)</dt><dd className="tabular">{fmt(truth[day - 1].true_storage_mm)} mm · error {fmt(truth[day - 1].estimate_error_mm)} mm</dd></div>}
                  </dl>
                </div>
              </CardContent>
            </Card>
            <SoilWaterChart rows={rows} truth={truth} name={`twin-${runId.slice(0, 8)}`} />
            <ChartFrame name={`uncertainty-${runId.slice(0, 8)}`} title="Belief uncertainty over the season" description="Ensemble standard deviation (mm). Grows with process noise between readings; drops after corrections (markers)." provenance={['estimated']}
              rows={uncertainty} columns={[{ key: 'day', label: 'Day' }, { key: 'std', label: 'σ (mm)' }, { key: 'theta', label: 'Mean θ (m³/m³)' }]}>
              <ResponsiveContainer>
                <ComposedChart data={uncertainty} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
                  <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="day" stroke={CHART.axis} fontSize={11} label={{ value: 'Day of season', position: 'insideBottom', offset: -10, fill: CHART.axis, fontSize: 11 }} />
                  <YAxis stroke={CHART.axis} fontSize={11} width={44} label={{ value: 'σ (mm)', angle: -90, position: 'insideLeft', fill: CHART.axis, fontSize: 11 }} />
                  <Tooltip {...tooltipStyle} />
                  <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
                  <Line dataKey="std" name="Ensemble σ" stroke={CHART.c1} dot={false} isAnimationActive={false} />
                  <Line dataKey="reading" name="Reading taken" stroke="none" dot={{ r: 4, fill: CHART.c2 }} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </ChartFrame>
            <StressChart rows={rows} truth={truth} name={`twin-stress-${runId.slice(0, 8)}`} />
            {evaluationMode && evaluation.data && (
              <Card><CardHeader><CardTitle className="flex items-center gap-2">Hidden reference parameters <ProvenanceBadge kind="truth" /></CardTitle><CardDescription>Random draw around the nominal soil profile; the twin only knew the prior distribution.</CardDescription></CardHeader>
                <CardContent><dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">{Object.entries(evaluation.data.hidden_parameters ?? {}).map(([k, v]) => <div key={k}><dt className="text-xs text-muted-foreground">{k}</dt><dd className="tabular">{Number(v).toFixed(4)}</dd></div>)}</dl></CardContent></Card>
            )}
          </div>
        )}
    </>
  );
}
