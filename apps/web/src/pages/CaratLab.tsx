import * as React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts';
import { Eye, EyeOff, FlaskConical, ShieldAlert } from 'lucide-react';
import { useDaily, useDecisions, useEvaluation, useRun, useRuns } from '@/api/hooks';
import type { DecisionTrace } from '@/api/types';
import { useWorkspace } from '@/app/workspace';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/misc';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EmptyState, ErrorPanel, Kpi, LoadingBlock, NeedScenario, Notice, PageHeader, ProvenanceBadge, Term } from '@/components/common';
import { DayStepper } from '@/components/DayStepper';
import { RunPicker } from '@/components/RunPicker';
import { ChartFrame, CHART, tooltipStyle } from '@/components/charts/ChartFrame';
import { QHeatmap } from '@/components/charts/PlotlyHeatmap';
import { fmt, STAGES } from '@/lib/utils';

/** Deterministic explanation built only from fields of the saved decision trace. */
export function explainDecision(t: DecisionTrace): string[] {
  const a = t.assessment_before;
  const lines: string[] = [];
  const b = t.initial_belief;
  lines.push(`Day ${t.day} (${STAGES[t.stage]}): the twin estimated ${b.mean_storage_mm.toFixed(1)} mm in the root zone (10–90 %: ${b.q10_storage_mm.toFixed(1)}–${b.q90_storage_mm.toFixed(1)} mm), ${(100 * b.depletion_fraction).toFixed(0)} % of TAW depleted, ${b.days_since_observation} day(s) since the last reading.`);
  lines.push(`The irrigation policy initially proposed ${t.initial_action_mm} mm.`);
  if (a) {
    lines.push(a.states_agree
      ? `All ${a.plausible_states?.length ?? 'plausible'} states preferred the same action (${a.belief_action_mm} mm), so estimated regret was ${a.regret_before.toExponential(2)} — a reading could not change the decision.`
      : `Plausible states disagreed on the best action; under the belief the best action was ${a.belief_action_mm} mm with estimated regret ${a.regret_before.toFixed(4)} reward units.`);
    if (t.observation_policy === 'carat') {
      lines.push(`Expected regret after a hypothetical reading: ${a.expected_regret_after.toFixed(4)} → gross VOI ${a.gross_voi.toFixed(4)}; minus cost ${a.observation_cost.toFixed(3)} and shadow price ${a.shadow_price === null ? 'n/a' : a.shadow_price.toFixed(3)} gives net VOI ${a.net_voi.toFixed(4)}.`);
    }
  }
  lines.push(t.observe ? `Decision: OBSERVE — ${t.observe_reason}.` : `Decision: SKIP the reading — ${t.observe_reason}.`);
  if (t.measurement) {
    lines.push(t.measurement.status === 'ok'
      ? `The sensor returned θ = ${t.measurement.theta_m3m3?.toFixed(4)} m³/m³ (σ ${t.measurement.noise_std_m3m3}); budget charged: ${t.measurement.charged ? 'yes' : 'no'}.`
      : `The reading attempt ended with status “${t.measurement.status}”; budget charged: ${t.measurement.charged ? 'yes' : 'no'}.`);
  }
  if (t.correction) {
    lines.push(t.correction.applied
      ? `Twin correction: Kalman gain ${t.correction.gain.toFixed(3)} moved the mean from ${t.correction.prior_mean_mm.toFixed(1)} to ${t.correction.posterior_mean_mm.toFixed(1)} mm and cut variance from ${t.correction.prior_var_mm2.toFixed(1)} to ${t.correction.posterior_var_mm2.toFixed(1)} mm².`
      : `The reading was not applied: ${t.correction.reason}.`);
  }
  if (t.proposed_mm !== t.initial_action_mm) lines.push(`After correction the policy proposed ${t.proposed_mm} mm.`);
  lines.push(`Risk manager: ${t.risk.reasons.length ? t.risk.reasons.join('; ') : 'no adjustment'} → applied ${t.applied_mm} mm.${t.risk.risk_flags.length ? ` Flags: ${t.risk.risk_flags.join(', ')}.` : ''}`);
  return lines;
}

function DecisionDetail({ trace, truth }: { trace: DecisionTrace; truth?: { true_storage_mm: number } | null }) {
  const a = trace.assessment_before;
  const after = trace.assessment_after;
  const candidates = a ? a.candidate_actions_mm.map((x, i) => ({
    action: `${x} mm`, expected: a.expected_values[i], p_best: a.prob_action_best[i],
    regret: (a.plausible_states ?? []).reduce((s, st) => s + st.weight * (Math.max(...st.q_values) - st.q_values[i]), 0),
    p_stress: trace.risk.stress_probability[String(x)] ?? null,
  })) : [];
  const states = (a?.plausible_states ?? []).map((s) => ({ storage: s.storage_mm, best: s.best_action_mm, weight: s.weight, theta: s.theta_m3m3 }));
  const hyp = ((a?.diagnostics?.hypothetical_regret_after as number[] | undefined) ?? []).map((v, i) => ({ i: i + 1, regret_after: v }));
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Estimated soil water" value={fmt(trace.initial_belief.mean_storage_mm, 1)} unit="mm" provenance="estimated" hint={`± ${fmt(trace.initial_belief.std_storage_mm, 1)} mm`} />
        <Kpi label={<Term id="regret">Est. regret</Term>} value={a ? fmt(a.regret_before, 4) : '—'} provenance="model" />
        <Kpi label={<Term id="voi">Net VOI</Term>} value={a && trace.observation_policy === 'carat' ? fmt(a.net_voi, 4) : '—'} provenance="model" hint={trace.observation_policy !== 'carat' ? `obs. policy: ${trace.observation_policy}` : undefined} />
        <Kpi label="Reading" value={trace.observe ? 'Observe' : 'Skip'} provenance="simulated" hint={trace.measurement?.status} />
        <Kpi label="Proposed → applied" value={`${trace.proposed_mm} → ${trace.applied_mm}`} unit="mm" provenance="simulated" />
        <Kpi label="Readings left" value={String(trace.budgets.observations_remaining)} provenance="simulated" hint={`${fmt(trace.budgets.water_remaining_after_mm, 0)} mm water left`} />
      </div>
      <Card>
        <CardHeader><CardTitle>Why this decision?</CardTitle><CardDescription>Generated deterministically from the saved trace fields — no language model involved.</CardDescription></CardHeader>
        <CardContent><ol className="list-decimal space-y-1.5 pl-5 text-sm">{explainDecision(trace).map((l, i) => <li key={i}>{l}</li>)}</ol>
          {truth && <p className="mt-3 flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive-soft p-2 text-sm"><ShieldAlert className="size-4 text-destructive" aria-hidden /> Evaluation only: the simulated reference ended this day at {truth.true_storage_mm.toFixed(1)} mm. This value was not available when deciding.</p>}
        </CardContent>
      </Card>
      <Tabs defaultValue="actions">
        <TabsList>
          <TabsTrigger value="actions">Candidate actions</TabsTrigger>
          <TabsTrigger value="states">Plausible states</TabsTrigger>
          <TabsTrigger value="voi">Regret & VOI</TabsTrigger>
          <TabsTrigger value="correction">Twin correction</TabsTrigger>
          <TabsTrigger value="risk">Risk manager</TabsTrigger>
        </TabsList>
        <TabsContent value="actions">
          {!a ? <p className="text-sm text-muted-foreground">No CARAT assessment recorded.</p> : (
            <Card className="overflow-x-auto p-4">
              <table className="w-full text-sm">
                <caption className="mb-2 text-left text-xs text-muted-foreground">Same horizon ({String(a.diagnostics.horizon_days)} d) and objective for every action; forecast: {String(a.diagnostics.forecast_source)}.</caption>
                <thead className="text-left text-xs text-muted-foreground"><tr><th className="p-2">Action</th><th className="p-2">Σ w·Q̂ (reward units)</th><th className="p-2">P(best | belief)</th><th className="p-2">Regret if chosen</th><th className="p-2">P(stress tomorrow)</th></tr></thead>
                <tbody>{candidates.map((c) => (
                  <tr key={c.action} className={`border-t ${c.action === `${a.belief_action_mm} mm` ? 'bg-secondary font-medium' : ''}`}>
                    <td className="p-2">{c.action}{c.action === `${a.belief_action_mm} mm` && <Badge variant="primary" className="ml-2">belief-optimal</Badge>}{c.action === `${trace.initial_action_mm} mm` && <Badge variant="info" className="ml-2">policy</Badge>}</td>
                    <td className="tabular p-2">{c.expected.toFixed(4)}</td><td className="tabular p-2">{(100 * c.p_best).toFixed(0)} %</td><td className="tabular p-2">{c.regret.toFixed(4)}</td><td className="tabular p-2">{c.p_stress === null ? '—' : `${(100 * c.p_stress).toFixed(0)} %`}</td>
                  </tr>))}</tbody>
              </table>
            </Card>
          )}
        </TabsContent>
        <TabsContent value="states">
          {!states.length ? <p className="text-sm text-muted-foreground">Plausible-state detail is stored for single runs (not for bulk experiment cells).</p> : (
            <div className="grid gap-4 xl:grid-cols-2">
              <ChartFrame name={`states-day-${trace.day}`} title="Plausible states and their best action" description="Each dot is one ensemble member (weight shown in table view)." provenance={['estimated', 'model']}
                rows={states} columns={[{ key: 'storage', label: 'Storage (mm)' }, { key: 'theta', label: 'θ (m³/m³)' }, { key: 'best', label: 'Best action (mm)' }, { key: 'weight', label: 'Weight' }]} height={300}>
                <ResponsiveContainer>
                  <ComposedChart data={states} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
                    <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" />
                    <XAxis dataKey="storage" type="number" domain={['auto', 'auto']} stroke={CHART.axis} fontSize={11} label={{ value: 'Plausible storage (mm)', position: 'insideBottom', offset: -10, fill: CHART.axis, fontSize: 11 }} />
                    <YAxis dataKey="best" type="number" stroke={CHART.axis} fontSize={11} width={44} label={{ value: 'Best action (mm)', angle: -90, position: 'insideLeft', fill: CHART.axis, fontSize: 11 }} />
                    <Tooltip {...tooltipStyle} />
                    <Scatter dataKey="best" fill={CHART.c1} isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </ChartFrame>
              <Card className="p-4"><QHeatmap title="Q̂(state, action) across the ensemble" z={a!.plausible_states!.map((s) => s.q_values)} x={a!.candidate_actions_mm.map((x) => `${x}`)} y={a!.plausible_states!.map((s) => `${s.storage_mm.toFixed(1)}`)} /></Card>
            </div>
          )}
        </TabsContent>
        <TabsContent value="voi">
          {!a ? null : (
            <div className="grid gap-4 xl:grid-cols-2">
              <Card className="p-4">
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  <dt className="text-muted-foreground">Regret before reading</dt><dd className="tabular">{a.regret_before.toFixed(5)}</dd>
                  <dt className="text-muted-foreground">Expected regret after</dt><dd className="tabular">{a.expected_regret_after.toFixed(5)}</dd>
                  <dt className="text-muted-foreground">Gross VOI</dt><dd className="tabular">{a.gross_voi.toFixed(5)}</dd>
                  <dt className="text-muted-foreground">− Observation cost</dt><dd className="tabular">{a.observation_cost.toFixed(5)}</dd>
                  <dt className="text-muted-foreground">− Budget shadow price</dt><dd className="tabular">{a.shadow_price === null ? 'n/a (no budget)' : a.shadow_price.toFixed(5)}</dd>
                  <dt className="font-medium">= Net VOI</dt><dd className="tabular font-medium">{a.net_voi.toFixed(5)}</dd>
                  <dt className="text-muted-foreground">Regret of policy’s action</dt><dd className="tabular">{a.regret_policy_action === null ? '—' : a.regret_policy_action.toFixed(5)}</dd>
                  <dt className="text-muted-foreground">Decision</dt><dd>{trace.observe ? 'observe' : 'skip'} — {trace.observe_reason}</dd>
                </dl>
                <p className="mt-3 text-xs text-muted-foreground">Estimates under the twin’s model and the CARAT value function — not oracle regret computed with the hidden state. Units: reward units (10 mm irrigation = 0.1).</p>
              </Card>
              {hyp.length ? (
                <ChartFrame name={`hypothetical-day-${trace.day}`} title="Regret after each hypothetical reading" description={`${hyp.length} seeded draws from p(z | belief); mean = expected regret after.`} provenance={['model']}
                  rows={hyp} columns={[{ key: 'i', label: 'Draw' }, { key: 'regret_after', label: 'Regret after' }]} height={260}>
                  <ResponsiveContainer>
                    <BarChart data={hyp} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
                      <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="i" stroke={CHART.axis} fontSize={11} label={{ value: 'Hypothetical reading #', position: 'insideBottom', offset: -10, fill: CHART.axis, fontSize: 11 }} />
                      <YAxis stroke={CHART.axis} fontSize={11} width={56} />
                      <Tooltip {...tooltipStyle} />
                      <ReferenceLine y={a.regret_before} stroke={CHART.c3} strokeDasharray="4 4" label={{ value: 'regret before', fill: CHART.c3, fontSize: 10, position: 'insideTopRight' }} />
                      <Bar dataKey="regret_after" name="Regret after" fill={CHART.c2} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartFrame>
              ) : <Card className="p-4 text-sm text-muted-foreground">{String(a.diagnostics.voi_shortcut ?? a.diagnostics.voi_skipped ?? 'No hypothetical readings were drawn.')}</Card>}
            </div>
          )}
        </TabsContent>
        <TabsContent value="correction">
          {!trace.correction ? <p className="text-sm text-muted-foreground">{trace.observe ? `Reading ${trace.measurement?.status ?? ''}; no correction applied (method may disable correction).` : 'No reading was taken on this day, so the twin was not corrected.'}</p> : (
            <Card className="p-4">
              <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                <div><dt className="text-xs text-muted-foreground">Prior mean / variance</dt><dd className="tabular">{trace.correction.prior_mean_mm.toFixed(2)} mm / {trace.correction.prior_var_mm2.toFixed(2)} mm²</dd></div>
                <div><dt className="text-xs text-muted-foreground">Measurement (as storage)</dt><dd className="tabular">{trace.correction.measurement_mm.toFixed(2)} mm</dd></div>
                <div><dt className="text-xs text-muted-foreground">Gain K = P/(P+R)</dt><dd className="tabular">{trace.correction.gain.toFixed(4)}</dd></div>
                <div><dt className="text-xs text-muted-foreground">Posterior mean / variance</dt><dd className="tabular">{trace.correction.posterior_mean_mm.toFixed(2)} mm / {trace.correction.posterior_var_mm2.toFixed(2)} mm²</dd></div>
              </dl>
              {after && <p className="mt-3 text-sm">After correction: belief-optimal action {after.belief_action_mm} mm, estimated regret {after.regret_before.toFixed(5)} (was {a?.regret_before.toFixed(5)}).</p>}
            </Card>
          )}
        </TabsContent>
        <TabsContent value="risk">
          <Card className="p-4">
            <div className="mb-2 flex flex-wrap gap-2"><Badge variant="outline">hard: {trace.risk.constraint_status}</Badge><Badge variant={trace.risk.soft_layer_enabled ? 'success' : 'outline'}>soft layer {trace.risk.soft_layer_enabled ? 'on' : 'off (ablation)'}</Badge>
              {trace.risk.risk_flags.map((f) => <Badge key={f} variant="warning">{f}</Badge>)}</div>
            <p className="text-sm">Proposed {trace.risk.proposed_mm} mm → hard-projected {trace.risk.hard_projected_mm} mm → applied {trace.risk.applied_mm} mm.</p>
            {trace.risk.reasons.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm">{trace.risk.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
            <p className="mt-3 text-xs text-muted-foreground">Predicted stress (1−Ks) quantiles for the applied action across plausible states: p10 {trace.risk.predicted_stress_quantiles.p10}, p50 {trace.risk.predicted_stress_quantiles.p50}, p90 {trace.risk.predicted_stress_quantiles.p90}. These are uncertain model estimates; hard limits are the only guarantees.</p>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function CaratLab() {
  const ws = useWorkspace();
  const [params, setParams] = useSearchParams();
  const runs = useRuns(ws.scenarioId);
  const caratRuns = (runs.data ?? []).filter((r) => r.method.includes('carat'));
  const runId = params.get('run') ?? caratRuns[0]?.id ?? runs.data?.[0]?.id ?? null;
  const run = useRun(runId);
  const daily = useDaily(runId);
  const [day, setDay] = React.useState(1);
  const [evaluationMode, setEvaluationMode] = React.useState(false);
  const decision = useDecisions(runId, day);
  const evaluation = useEvaluation(runId, evaluationMode);
  if (!ws.loading && !ws.scenario) return <><PageHeader title="CARAT Decision Lab" /><NeedScenario /></>;
  const rows = daily.data?.rows ?? [];
  const timeline = rows.map((r) => ({ day: r.day, regret: r.est_regret, gross: r.gross_voi, net: r.net_voi, observed: r.observed ? (r.gross_voi ?? r.est_regret ?? 0) : null, applied: r.applied_mm }));
  const trace = decision.data?.rows[0];
  const s = run.data?.summary;

  return (
    <>
      <PageHeader title="CARAT Decision Lab" description={<>Counterfactual Action-Regret and Adaptive Twin Correction — a <strong>proposed</strong> method. Inspect, day by day, whether a soil reading was worth taking and what it changed.</>}
        actions={<Button variant="outline" asChild><Link to="/simulation?start=lookahead_carat">Run CARAT planner (no PPO)</Link></Button>} />
      <Card className="mb-4 flex flex-wrap items-end justify-between gap-4 p-4">
        <RunPicker scenarioId={ws.scenarioId} value={runId} onChange={(id) => { setParams({ run: id }); setDay(1); }} label="Run to replay (CARAT runs first)" />
        <div className="flex items-center gap-2 text-sm">
          {evaluationMode ? <Eye className="size-4 text-destructive" aria-hidden /> : <EyeOff className="size-4 text-muted-foreground" aria-hidden />}
          <Switch id="carat-eval" checked={evaluationMode} onCheckedChange={setEvaluationMode} />
          <label htmlFor="carat-eval">Post-run evaluation (show hidden reference)</label>
        </div>
      </Card>
      {!runId ? <EmptyState icon={FlaskConical} title="No run to replay" description="Run full CARAT (needs a PPO model) or the CARAT planner (no PPO needed) from the simulator."
        action={<><Button asChild><Link to="/simulation?start=lookahead_carat">Run CARAT planner</Link></Button><Button variant="outline" asChild><Link to="/training">Train PPO</Link></Button></>} /> :
        daily.isError ? <ErrorPanel error={daily.error} retry={() => daily.refetch()} /> : daily.isLoading || !s ? <LoadingBlock rows={4} /> : (
          <div className="flex flex-col gap-4">
            {!run.data!.method.includes('carat') && <Notice>This run uses observation policy “{run.data!.method}”. Regret is logged as a diagnostic; VOI-driven decisions only occur in CARAT runs.</Notice>}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <Kpi label="Method" value={run.data!.method_code} hint={run.data!.method_label} />
              <Kpi label="Readings used" value={String(s.observation_count)} unit={`of ${s.observation_count + s.observations_remaining}`} provenance="simulated" />
              <Kpi label="Mean est. regret" value={fmt(s.estimated_regret_mean, 4)} provenance="model" />
              <Kpi label="Mean gross VOI" value={fmt(s.gross_voi_mean, 4)} provenance="model" />
              <Kpi label="Decision changes" value={s.decision_disagreement_rate === null ? '—' : `${fmt(100 * s.decision_disagreement_rate, 0)} %`} hint="initial ≠ final proposal" provenance="simulated" />
            </div>
            <ChartFrame name={`carat-timeline-${runId.slice(0, 8)}`} title="Estimated regret and value of information over the season" description="Dots: days a reading was taken. Click the table view for exact values." provenance={['model']}
              rows={timeline} columns={[{ key: 'day', label: 'Day' }, { key: 'regret', label: 'Est. regret' }, { key: 'gross', label: 'Gross VOI' }, { key: 'net', label: 'Net VOI' }, { key: 'applied', label: 'Applied (mm)' }]}>
              <ResponsiveContainer>
                <ComposedChart data={timeline} margin={{ top: 8, right: 12, bottom: 18, left: 4 }} onClick={(e) => { if (e && typeof e.activeLabel === 'number') setDay(e.activeLabel); }}>
                  <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="day" stroke={CHART.axis} fontSize={11} label={{ value: 'Day of season', position: 'insideBottom', offset: -10, fill: CHART.axis, fontSize: 11 }} />
                  <YAxis stroke={CHART.axis} fontSize={11} width={56} label={{ value: 'Reward units', angle: -90, position: 'insideLeft', fill: CHART.axis, fontSize: 11 }} />
                  <Tooltip {...tooltipStyle} />
                  <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
                  <ReferenceLine y={0} stroke={CHART.axis} />
                  <ReferenceLine x={day} stroke={CHART.c4} strokeDasharray="3 3" />
                  <Line dataKey="regret" name="Est. regret" stroke={CHART.c3} dot={false} isAnimationActive={false} />
                  <Line dataKey="gross" name="Gross VOI" stroke={CHART.c2} dot={false} isAnimationActive={false} />
                  <Line dataKey="net" name="Net VOI" stroke={CHART.c1} dot={false} strokeDasharray="4 3" isAnimationActive={false} />
                  <Scatter dataKey="observed" name="Reading taken" fill={CHART.c1} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </ChartFrame>
            <Card>
              <CardHeader><CardTitle>Decision replay</CardTitle><CardDescription>Auditable trace for one day: belief → candidate actions → regret → VOI → observe/skip → correction → risk → applied.</CardDescription></CardHeader>
              <CardContent className="flex flex-col gap-4">
                <DayStepper day={day} max={rows.length} onChange={setDay} />
                <div className="flex flex-wrap gap-1" aria-label="Jump to observation days">
                  {rows.filter((r) => r.observation_attempted).map((r) => <Button key={r.day} size="sm" variant={r.day === day ? 'default' : 'outline'} onClick={() => setDay(r.day)}>Day {r.day}</Button>)}
                  {!rows.some((r) => r.observation_attempted) && <span className="text-xs text-muted-foreground">No readings were requested in this run.</span>}
                </div>
                {evaluationMode && <ProvenanceBadge kind="truth" />}
                {decision.isLoading ? <LoadingBlock rows={3} /> : decision.isError ? <ErrorPanel error={decision.error} /> : trace && <DecisionDetail trace={trace} truth={evaluationMode ? evaluation.data?.rows[day - 1] ?? null : null} />}
              </CardContent>
            </Card>
          </div>
        )}
    </>
  );
}
