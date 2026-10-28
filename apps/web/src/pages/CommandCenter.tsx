import { Link, useNavigate } from 'react-router-dom';
import { CheckCircle2, Circle, CloudRain, Droplets, Gauge, Leaf, Radar, ServerCog, Sprout, Wheat } from 'lucide-react';
import { useDatasets, useExperiments, useExports, useHealth, useJobs, useModels, useRuns } from '@/api/hooks';
import { useWorkspace } from '@/app/workspace';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState, ErrorPanel, Kpi, LoadingBlock, Notice, PageHeader, ProvenanceBadge, StatusBadge, Term, datasetProvenance } from '@/components/common';
import { JobCard } from '@/components/JobCard';
import { fmt, relativeTime, shortId } from '@/lib/utils';

export default function CommandCenter() {
  const ws = useWorkspace();
  const health = useHealth();
  const runs = useRuns(ws.scenarioId);
  const allRuns = useRuns();
  const models = useModels();
  const experiments = useExperiments();
  const exports = useExports();
  const datasets = useDatasets();
  const jobs = useJobs('&status=queued,running');
  const navigate = useNavigate();
  const dataset = datasets.data?.find((d) => d.id === ws.scenario?.dataset_id);
  const latest = runs.data?.[0];
  const s = latest?.summary;

  const steps = [
    { done: ws.projects.length > 0, label: 'Create or select a field project', to: '/projects' },
    { done: !!ws.scenario?.dataset_id, label: 'Attach weather data to the scenario', to: '/data' },
    { done: (allRuns.data?.length ?? 0) > 0, label: 'Run a baseline irrigation simulation', to: '/simulation' },
    { done: (models.data?.length ?? 0) > 0, label: 'Train a quick PPO model', to: '/training' },
    { done: !!allRuns.data?.some((r) => r.method.includes('carat')), label: 'Run a CARAT-controlled season', to: '/carat' },
    { done: !!experiments.data?.some((e) => e.status === 'succeeded'), label: 'Compare against baselines', to: '/experiments' },
    { done: (exports.data?.length ?? 0) > 0, label: 'Export results with a manifest', to: '/reports' },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Irrigation intelligence · local research platform"
        title="Command Center"
        description={<>Status of your active field, the latest simulated season and the research pipeline. Every number links back to a saved run.</>}
        actions={
          <>
            <Button variant="outline" onClick={() => navigate('/simulation')}><Droplets aria-hidden />Run simulation</Button>
            <Button onClick={() => navigate('/carat')}><Radar aria-hidden />Open CARAT Lab</Button>
          </>
        }
      />
      {health.isError && <div className="mb-4"><ErrorPanel title="API unavailable" error={health.error} retry={() => health.refetch()} /></div>}

      <Card className="mb-6 overflow-hidden border-0 bg-brand text-brand-foreground">
        <div className="flex flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#9fdcc4]">Active field</p>
            <h2 className="mt-1 text-xl font-semibold">{ws.project?.name ?? 'No project selected'}</h2>
            <p className="mt-1 text-sm text-brand-foreground/80">
              {ws.scenario
                ? `${ws.scenario.name} · ${ws.scenario.crop_profile} on ${ws.scenario.soil_profile.replace('_', ' ')} · planting ${ws.scenario.planting_mmdd} · ${ws.scenario.seasonal_budget_mm} mm water budget · ${ws.scenario.observation_budget} soil readings / season`
                : 'Create a project or explore the synthetic sample field to begin.'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {dataset && <ProvenanceBadge kind={datasetProvenance(dataset.source)} className="bg-white/90" />}
            {!ws.project && <Button variant="secondary" asChild><Link to="/projects">Set up a field</Link></Button>}
          </div>
        </div>
      </Card>

      {dataset?.is_synthetic && (
        <Notice tone="warning" className="mb-6">
          <strong>Synthetic demonstration data.</strong> The active scenario uses generated weather (seeded, documented). Results illustrate the method; they are not historical or field outcomes.
        </Notice>
      )}

      <section aria-labelledby="kpi-title" className="mb-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 id="kpi-title" className="text-base font-semibold">Latest season {latest ? <span className="font-normal text-muted-foreground">— {latest.method_label}, season {latest.season_id} ({latest.split}), seed {latest.seed}</span> : null}</h2>
          {latest && <Button variant="link" asChild><Link to={`/simulation?run=${latest.id}`}>Inspect run {shortId(latest.id)}</Link></Button>}
        </div>
        {runs.isLoading ? <LoadingBlock rows={1} /> : !latest ? (
          <EmptyState icon={Droplets} title="No simulation run yet" description="KPIs appear after a run completes — nothing here is pre-filled."
            action={<Button asChild><Link to="/simulation">Run a fixed-schedule baseline</Link></Button>} />
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Kpi icon={Droplets} label="Seasonal irrigation" value={fmt(s!.seasonal_irrigation_mm, 0)} unit="mm" provenance="simulated" hint={`budget ${ws.scenario?.seasonal_budget_mm ?? '—'} mm`} />
            <Kpi icon={CloudRain} label="Seasonal rain" value={fmt(s!.seasonal_rain_mm, 0)} unit="mm" provenance={datasetProvenance(dataset?.source)} />
            <Kpi icon={Leaf} label={<Term id="proxy">Yield proxy</Term>} value={fmt(s!.yield_proxy_t_ha, 2)} unit="t/ha" provenance="proxy" />
            <Kpi icon={Wheat} label={<Term id="aquacrop">AquaCrop yield</Term>} value={fmt(s!.aquacrop?.aquacrop_simulated_dry_yield_t_ha, 2)} unit="t/ha" provenance="aquacrop"
              hint={s!.aquacrop?.error ? 'evaluation failed' : s!.aquacrop ? undefined : 'not evaluated'} />
            <Kpi icon={Gauge} label="Soil readings" value={String(s!.observation_count)} unit={`/ ${ws.scenario?.observation_budget ?? '—'}`} provenance="simulated" />
            <Kpi icon={Sprout} label="Stress days" value={String(s!.stress_days)} unit="days" provenance="simulated" hint={`Σ(1−Ks) ${fmt(s!.cumulative_stress, 1)}`} />
          </div>
        )}
      </section>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader><CardTitle>Recent runs</CardTitle><CardDescription>All scenarios · newest first</CardDescription></CardHeader>
          <CardContent>
            {allRuns.isError ? <ErrorPanel error={allRuns.error} retry={() => allRuns.refetch()} /> : allRuns.isLoading ? <LoadingBlock rows={2} /> : !allRuns.data?.length ? (
              <p className="text-sm text-muted-foreground">No runs yet.</p>
            ) : (
              <ul className="divide-y">
                {allRuns.data.slice(0, 6).map((r) => (
                  <li key={r.id}>
                    <Link to={`/simulation?run=${r.id}`} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm hover:text-primary">
                      <span className="min-w-0"><Badge variant="outline" className="mr-2 font-mono">{r.method_code}</Badge>{r.method_label} · season {r.season_id} · seed {r.seed}</span>
                      <span className="tabular text-xs text-muted-foreground">{fmt(r.summary.seasonal_irrigation_mm, 0)} mm · proxy {fmt(r.summary.yield_proxy_t_ha, 2)} t/ha · {relativeTime(r.created_at)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Getting started</CardTitle><CardDescription>Progress is derived from saved data.</CardDescription></CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-2 text-sm">
              {steps.map((step) => (
                <li key={step.label}>
                  <Link to={step.to} className="flex items-center gap-2 rounded-md p-1 hover:bg-muted">
                    {step.done ? <CheckCircle2 className="size-4 text-success" aria-label="done" /> : <Circle className="size-4 text-muted-foreground" aria-label="to do" />}
                    <span className={step.done ? 'text-muted-foreground line-through' : ''}>{step.label}</span>
                  </Link>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader><CardTitle>Active jobs</CardTitle><CardDescription>Heavy work runs in the separate worker process.</CardDescription></CardHeader>
          <CardContent className="flex flex-col gap-3">
            {!jobs.data?.length ? <p className="text-sm text-muted-foreground">No queued or running jobs.</p> : jobs.data.slice(0, 3).map((j) => <JobCard key={j.id} jobId={j.id} title={`${j.kind} job`} />)}
            {experiments.data && experiments.data.length > 0 && (
              <div>
                <h3 className="mb-2 mt-2 text-sm font-semibold">Recent experiments</h3>
                <ul className="divide-y text-sm">
                  {experiments.data.slice(0, 4).map((e) => (
                    <li key={e.id} className="flex items-center justify-between gap-2 py-2">
                      <Link className="truncate hover:text-primary" to={`/experiments?id=${e.id}`}>{e.name}</Link>
                      <span className="flex items-center gap-2"><span className="text-xs text-muted-foreground">{e.n_runs ?? 0} runs</span><StatusBadge status={e.status} /></span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><ServerCog className="size-4" aria-hidden />System status</CardTitle></CardHeader>
          <CardContent>
            {health.data ? (
              <dl className="grid grid-cols-2 gap-y-2 text-sm">
                <dt className="text-muted-foreground">API / database</dt><dd><Badge variant="success">{health.data.api} / {health.data.database}</Badge></dd>
                <dt className="text-muted-foreground">Worker</dt><dd><Badge variant={health.data.worker.status === 'online' ? 'success' : 'warning'}>{health.data.worker.status.replace('_', ' ')}</Badge></dd>
                <dt className="text-muted-foreground">AquaCrop-OSPy</dt><dd><Badge variant={health.data.aquacrop.available ? 'success' : 'warning'}>{health.data.aquacrop.available ? `v${health.data.aquacrop.detail}` : 'unavailable'}</Badge></dd>
                <dt className="text-muted-foreground">Trained models</dt><dd className="tabular">{health.data.models}</dd>
                <dt className="text-muted-foreground">Saved runs</dt><dd className="tabular">{health.data.runs}</dd>
                <dt className="text-muted-foreground">Datasets</dt><dd className="tabular">{health.data.datasets}</dd>
              </dl>
            ) : health.isLoading ? <LoadingBlock rows={2} /> : null}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
