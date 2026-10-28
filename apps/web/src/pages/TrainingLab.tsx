import * as React from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { BrainCircuit, Cpu, Play } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { mutations, useDefaults, useInvalidate, useJobs, useModel, useModels, useSeasons } from '@/api/hooks';
import { useJobEvents } from '@/api/progress';
import { useWorkspace } from '@/app/workspace';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/misc';
import { EmptyState, ErrorPanel, Field, LoadingBlock, NeedScenario, Notice, PageHeader, Term } from '@/components/common';
import { JobCard } from '@/components/JobCard';
import { ChartFrame, CHART, tooltipStyle } from '@/components/charts/ChartFrame';
import { cn, fmt, relativeTime, shortId } from '@/lib/utils';

const PRESETS = [
  { key: 'cpu_quick', title: 'Quick smoke', cls: 'Functional test only — not research quality', warn: null },
  { key: 'cpu_standard', title: 'Standard CPU', cls: 'Multi-seed with validation-based checkpoint selection', warn: 'Typically tens of minutes per seed on a laptop CPU; actual time depends on hardware.' },
  { key: 'cpu_research', title: 'Research CPU', cls: 'Longer multi-seed training with wall-time cap', warn: 'Can take hours on CPU. Bounded by max_wall_seconds; cancellable at any time.' },
] as const;

const hpSchema = z.object({
  learning_rate: z.coerce.number().min(1e-6).max(1e-2),
  n_steps: z.coerce.number().int().min(64).max(8192),
  batch_size: z.coerce.number().int().min(16).max(1024),
  gamma: z.coerce.number().min(0.8).max(0.9999),
  ent_coef: z.coerce.number().min(0).max(0.1),
  total_timesteps: z.coerce.number().int().min(256).max(3_000_000),
  seeds: z.string().regex(/^\s*\d+(\s*,\s*\d+)*\s*$/, 'Comma-separated integers'),
}).refine((v) => v.batch_size <= v.n_steps, { message: 'batch_size must not exceed n_steps', path: ['batch_size'] });
type HpForm = z.infer<typeof hpSchema>;

function LiveCurve({ jobId }: { jobId: string }) {
  const { events } = useJobEvents(jobId);
  const points = events.filter((e) => e.metric_name && e.metric_value !== null).map((e) => ({ step: e.current_step, value: e.metric_value as number, metric: e.metric_name, phase: e.phase }));
  if (!points.length) return <p className="text-sm text-muted-foreground">No evaluation point logged yet — the curve appears when the first validation evaluation completes. Nothing is extrapolated.</p>;
  return (
    <ChartFrame name={`live-curve-${jobId.slice(0, 8)}`} title="Live training signal" description={`${points[0].metric} from real evaluation callbacks (reward units).`} provenance={['simulated']}
      rows={points} columns={[{ key: 'step', label: 'Global timestep' }, { key: 'value', label: 'Metric value' }, { key: 'phase', label: 'Phase' }]} height={240}>
      <ResponsiveContainer>
        <ComposedChart data={points} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
          <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="step" stroke={CHART.axis} fontSize={11} label={{ value: 'Timesteps', position: 'insideBottom', offset: -10, fill: CHART.axis, fontSize: 11 }} />
          <YAxis stroke={CHART.axis} fontSize={11} width={52} />
          <Tooltip {...tooltipStyle} />
          <Line dataKey="value" name="Validation / training reward" stroke={CHART.c1} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

function ModelDetail({ id }: { id: string }) {
  const model = useModel(id);
  if (model.isLoading) return <LoadingBlock rows={2} />;
  if (model.isError) return <ErrorPanel error={model.error} />;
  const m = model.data!;
  const hist = m.manifest?.history ?? [];
  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
        <div><dt className="text-xs text-muted-foreground">Preset · seed</dt><dd>{m.preset} · {m.seed}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Timesteps</dt><dd className="tabular">{m.actual_timesteps.toLocaleString()} ({m.manifest?.stop_reason})</dd></div>
        <div><dt className="text-xs text-muted-foreground">Checkpoint</dt><dd className="tabular">{m.checkpoint_bytes ? `${fmt(m.checkpoint_bytes / 1024, 0)} KiB` : '—'} · sha {m.checkpoint_sha256.slice(0, 12)}…</dd></div>
        <div><dt className="text-xs text-muted-foreground">Selection</dt><dd>{m.manifest?.selection}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Train seasons</dt><dd>{m.manifest?.train_seasons.join(', ')}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Validation seasons</dt><dd>{m.manifest?.validation_seasons.join(', ') || '—'}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Validation reward</dt><dd className="tabular">{fmt(m.validation.mean_reward, 3)} ± {fmt(m.validation.std_reward, 3)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Validation yield proxy ratio · irrigation</dt><dd className="tabular">{fmt(m.validation.mean_yield_ratio_proxy, 3)} · {fmt(m.validation.mean_irrigation_mm, 0)} mm</dd></div>
      </dl>
      {hist.length > 0 ? (
        <ChartFrame name={`curve-${id.slice(0, 8)}`} title="Logged learning curve" description="Training episode reward (moving window) and deterministic validation reward at each evaluation." provenance={['simulated']}
          rows={hist as unknown as Record<string, unknown>[]} columns={[{ key: 'timesteps', label: 'Timesteps' }, { key: 'train_mean_episode_reward', label: 'Train reward' }, { key: 'validation_mean_reward', label: 'Validation reward' }]} height={240}>
          <ResponsiveContainer>
            <ComposedChart data={hist} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
              <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="timesteps" stroke={CHART.axis} fontSize={11} label={{ value: 'Timesteps', position: 'insideBottom', offset: -10, fill: CHART.axis, fontSize: 11 }} />
              <YAxis stroke={CHART.axis} fontSize={11} width={52} label={{ value: 'Episode reward', angle: -90, position: 'insideLeft', fill: CHART.axis, fontSize: 11 }} />
              <Tooltip {...tooltipStyle} />
              <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
              <Line dataKey="train_mean_episode_reward" name="Train (recent episodes)" stroke={CHART.c3} isAnimationActive={false} />
              <Line dataKey="validation_mean_reward" name="Validation (deterministic)" stroke={CHART.c1} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartFrame>
      ) : <p className="text-sm text-muted-foreground">No evaluation points were logged for this model.</p>}
      <div className="flex flex-wrap gap-2">
        <Button asChild><Link to="/simulation?start=carat_full">Evaluate with full CARAT</Link></Button>
        <Button variant="outline" asChild><Link to="/experiments">Benchmark against baselines</Link></Button>
      </div>
    </div>
  );
}

export default function TrainingLab() {
  const ws = useWorkspace();
  const defaults = useDefaults();
  const seasons = useSeasons(ws.scenarioId);
  const models = useModels(ws.scenarioId);
  const trainingJobs = useJobs('&kind=training');
  const refresh = useInvalidate();
  const [preset, setPreset] = React.useState<'cpu_quick' | 'cpu_standard' | 'cpu_research'>('cpu_quick');
  const [confirm, setConfirm] = React.useState(false);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedModel, setSelectedModel] = React.useState<string | null>(null);
  const p = defaults.data?.training_presets[preset];
  const form = useForm<HpForm>({
    resolver: zodResolver(hpSchema),
    values: p ? { learning_rate: Number(p.hyperparameters.learning_rate), n_steps: Number(p.hyperparameters.n_steps), batch_size: Number(p.hyperparameters.batch_size),
      gamma: Number(p.hyperparameters.gamma), ent_coef: Number(p.hyperparameters.ent_coef), total_timesteps: p.total_timesteps, seeds: p.seeds.join(', ') } : undefined,
  });
  const running = trainingJobs.data?.find((j) => j.status === 'queued' || j.status === 'running');
  const activeJob = jobId ?? running?.id ?? null;
  const modelId = selectedModel ?? models.data?.find((m) => m.selected)?.id ?? models.data?.[0]?.id ?? null;

  const submit = form.handleSubmit(async (v) => {
    if (!ws.scenarioId) return;
    setError(null);
    try {
      const job = await mutations.train({
        scenario_id: ws.scenarioId, preset, total_timesteps: v.total_timesteps, seeds: v.seeds.split(',').map((s) => Number(s.trim())),
        hyperparameters: { learning_rate: v.learning_rate, n_steps: v.n_steps, batch_size: v.batch_size, gamma: v.gamma, ent_coef: v.ent_coef },
        confirm_long_run: confirm,
      });
      setJobId(job.id);
      refresh('jobs');
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  if (!ws.loading && !ws.scenario) return <><PageHeader title="Model Training Lab" /><NeedScenario /></>;
  const err = form.formState.errors;
  const split = seasons.data?.split;

  return (
    <>
      <PageHeader title="Model Training Lab" description={<>Train a <Term id="ppo">PPO</Term> irrigation policy on training seasons; validation seasons select the checkpoint; test seasons stay untouched.</>} />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Cpu className="size-4" aria-hidden />New training job</CardTitle><CardDescription>Runs in the worker (max one training job at a time). Never unbounded.</CardDescription></CardHeader>
          <CardContent>
            <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
              <fieldset className="grid gap-2 sm:grid-cols-3">
                <legend className="mb-2 text-sm font-medium">Preset</legend>
                {PRESETS.map((x) => {
                  const d = defaults.data?.training_presets[x.key];
                  return (
                    <label key={x.key} className={cn('flex cursor-pointer flex-col gap-1 rounded-lg border p-3 text-sm', preset === x.key && 'border-primary bg-secondary')}>
                      <input type="radio" name="preset" value={x.key} checked={preset === x.key} onChange={() => { setPreset(x.key); setConfirm(false); }} className="sr-only" />
                      <span className="font-semibold">{x.title}</span>
                      <span className="tabular text-xs text-muted-foreground">{d ? `${d.total_timesteps.toLocaleString()} steps × ${d.seeds.length} seed(s)` : '…'}</span>
                      <span className="text-xs">{x.cls}</span>
                    </label>
                  );
                })}
              </fieldset>
              {PRESETS.find((x) => x.key === preset)?.warn && (
                <Notice tone="warning">
                  {PRESETS.find((x) => x.key === preset)!.warn}
                  <label className="mt-2 flex items-center gap-2"><Checkbox checked={confirm} onCheckedChange={(c) => setConfirm(c === true)} aria-label="Confirm long CPU run" /> I understand this is a long CPU job.</label>
                </Notice>
              )}
              <details className="rounded-md border p-3">
                <summary className="cursor-pointer text-sm font-medium">Advanced hyperparameters</summary>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Field label="Total timesteps (per seed)" htmlFor="hp-steps" error={err.total_timesteps?.message} hint={preset === 'cpu_quick' ? 'Quick preset: ≤ 10,000' : undefined}><Input id="hp-steps" type="number" {...form.register('total_timesteps')} /></Field>
                  <Field label="Seeds" htmlFor="hp-seeds" error={err.seeds?.message}><Input id="hp-seeds" {...form.register('seeds')} /></Field>
                  <Field label="Learning rate" htmlFor="hp-lr" error={err.learning_rate?.message}><Input id="hp-lr" type="number" step="0.00001" {...form.register('learning_rate')} /></Field>
                  <Field label="n_steps (rollout)" htmlFor="hp-n" error={err.n_steps?.message}><Input id="hp-n" type="number" {...form.register('n_steps')} /></Field>
                  <Field label="Batch size" htmlFor="hp-b" error={err.batch_size?.message}><Input id="hp-b" type="number" {...form.register('batch_size')} /></Field>
                  <Field label="γ (discount)" htmlFor="hp-g" error={err.gamma?.message}><Input id="hp-g" type="number" step="0.001" {...form.register('gamma')} /></Field>
                  <Field label="Entropy coefficient" htmlFor="hp-e" error={err.ent_coef?.message}><Input id="hp-e" type="number" step="0.001" {...form.register('ent_coef')} /></Field>
                </div>
              </details>
              <Card className="bg-muted/50 p-3 text-xs">
                <p className="mb-1 font-semibold">Before you start</p>
                <ul className="grid gap-1 sm:grid-cols-2">
                  <li>Split: {split ? `${split.train.length} train / ${split.validation.length} val / ${split.test.length} test (held out)` : '—'}</li>
                  <li>Scenario hash: <span className="font-mono">{ws.scenario?.scenario_sha256?.slice(0, 12) ?? '—'}…</span></li>
                  <li>Policy: MlpPolicy {String(p?.hyperparameters.net_arch ?? '')} · actions {defaults.data?.actions_mm.join('/')} mm</li>
                  <li>Reward λ: water {defaults.data?.reward.water}, stress {defaults.data?.reward.stress}, violation {defaults.data?.reward.violation}, yield {defaults.data?.reward.terminal_yield}</li>
                </ul>
              </Card>
              {split && !split.train.length && <Notice tone="warning">No training seasons available: {split.rule}.</Notice>}
              <Button type="submit" disabled={!!running || (preset !== 'cpu_quick' && !confirm) || !split?.train.length}><Play aria-hidden />{running ? 'A training job is already active' : 'Queue training'}</Button>
              {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            </form>
          </CardContent>
        </Card>
        <div className="flex flex-col gap-4">
          {activeJob ? (
            <>
              <JobCard jobId={activeJob} title="PPO training" />
              <LiveCurve jobId={activeJob} />
            </>
          ) : <EmptyState icon={BrainCircuit} title="No training run yet" description="Start the quick preset to verify the pipeline. Its result is a functional checkpoint, not evidence of policy quality." />}
        </div>
      </div>

      <Card className="mt-6">
        <CardHeader><CardTitle>Models for this scenario</CardTitle><CardDescription>Only checkpoints that were saved, reloaded and passed an inference check are listed.</CardDescription></CardHeader>
        <CardContent>
          {models.isLoading ? <LoadingBlock rows={2} /> : !models.data?.length ? <p className="text-sm text-muted-foreground">No trained models. PPO-based methods stay unavailable until one exists — no placeholder recommendations are shown.</p> : (
            <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
              <ul className="flex flex-col gap-2">
                {models.data.map((m) => (
                  <li key={m.id}>
                    <button type="button" onClick={() => setSelectedModel(m.id)} aria-pressed={m.id === modelId} className={cn('w-full rounded-md border p-3 text-left text-sm', m.id === modelId && 'border-primary bg-secondary')}>
                      <span className="flex flex-wrap items-center gap-1 font-medium">{m.preset} · seed {m.seed}{m.selected && <Badge variant="success">selected</Badge>}{!m.research_quality && <Badge variant="warning">smoke</Badge>}</span>
                      <span className="tabular text-xs text-muted-foreground">{m.actual_timesteps.toLocaleString()} steps · val {fmt(m.validation.mean_reward, 2)} · {relativeTime(m.created_at)} · {shortId(m.id)}</span>
                    </button>
                  </li>
                ))}
              </ul>
              {modelId && <ModelDetail id={modelId} />}
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
