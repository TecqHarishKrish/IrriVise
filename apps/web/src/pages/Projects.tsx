import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useSearchParams } from 'react-router-dom';
import { Archive, ArchiveRestore, CheckCircle2, Pencil, Plus, Sprout, TestTube2 } from 'lucide-react';
import { mutations, useDatasets, useDefaults, useInvalidate, useProjects, useScenarios } from '@/api/hooks';
import { errorMessage } from '@/api/client';
import type { Project, Scenario } from '@/api/types';
import { useWorkspace } from '@/app/workspace';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input, Select, Textarea } from '@/components/ui/input';
import { Switch } from '@/components/ui/misc';
import { EmptyState, ErrorPanel, Field, LoadingBlock, Notice, PageHeader, Term } from '@/components/common';
import { cn } from '@/lib/utils';

const noMarkup = (v: string) => !/[<>]/.test(v);
const projectSchema = z.object({
  name: z.string().trim().min(2, 'At least 2 characters').max(100).refine(noMarkup, 'Angle brackets are not allowed'),
  description: z.string().max(1000).refine(noMarkup, 'Angle brackets are not allowed'),
});
type ProjectForm = z.infer<typeof projectSchema>;

const mmdd = /^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;
const scenarioSchema = z.object({
  name: z.string().trim().min(2, 'At least 2 characters').max(100).refine(noMarkup, 'Angle brackets are not allowed'),
  latitude: z.coerce.number().min(-90, 'Latitude must be ≥ −90').max(90, 'Latitude must be ≤ 90'),
  longitude: z.coerce.number().min(-180, 'Longitude must be ≥ −180').max(180, 'Longitude must be ≤ 180'),
  soil_profile: z.string().min(1),
  planting_mmdd: z.string().regex(mmdd, 'Use MM-DD, e.g. 06-15').refine((v) => v !== '02-29', 'Leap day is not allowed'),
  daily_max_mm: z.coerce.number().min(0, '≥ 0 mm').max(100, '≤ 100 mm/day'),
  seasonal_budget_mm: z.coerce.number().min(0, '≥ 0 mm').max(3000, '≤ 3000 mm'),
  observation_budget: z.coerce.number().int('Whole number').min(0, '≥ 0').max(365, '≤ 365'),
  sensor_noise_m3m3: z.coerce.number().min(0).max(0.2, '≤ 0.2 m³/m³'),
  sensor_mode: z.enum(['nominal', 'missing', 'biased', 'stuck', 'delayed']),
  initial_fraction_mean: z.coerce.number().min(0).max(1),
  dataset_id: z.string().nullable(),
});
type ScenarioForm = z.infer<typeof scenarioSchema>;

function ProjectDialog({ open, onOpenChange, project }: { open: boolean; onOpenChange: (o: boolean) => void; project?: Project }) {
  const refresh = useInvalidate();
  const ws = useWorkspace();
  const [error, setError] = React.useState<string | null>(null);
  const form = useForm<ProjectForm>({ resolver: zodResolver(projectSchema), values: { name: project?.name ?? '', description: project?.description ?? '' } });
  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const saved = project ? await mutations.updateProject({ id: project.id, ...values }) : await mutations.createProject(values);
      refresh('projects');
      if (!project) ws.select(saved.id);
      onOpenChange(false);
      form.reset();
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  const err = form.formState.errors;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{project ? 'Edit project' : 'New field project'}</DialogTitle><DialogDescription>Projects group field scenarios. Crop: maize (FAO-56 profile).</DialogDescription></DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          <Field label="Project name" htmlFor="p-name" error={err.name?.message}><Input id="p-name" aria-invalid={!!err.name} {...form.register('name')} /></Field>
          <Field label="Description" htmlFor="p-desc" error={err.description?.message}><Textarea id="p-desc" {...form.register('description')} /></Field>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={form.formState.isSubmitting}>{project ? 'Save' : 'Create project'}</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ScenarioDialog({ open, onOpenChange, projectId, scenario }: { open: boolean; onOpenChange: (o: boolean) => void; projectId: string; scenario?: Scenario }) {
  const defaults = useDefaults();
  const datasets = useDatasets();
  const refresh = useInvalidate();
  const ws = useWorkspace();
  const [error, setError] = React.useState<string | null>(null);
  const sample = datasets.data?.find((d) => d.source === 'sample');
  const form = useForm<ScenarioForm>({
    resolver: zodResolver(scenarioSchema),
    values: scenario ? {
      name: scenario.name, latitude: scenario.latitude, longitude: scenario.longitude, soil_profile: scenario.soil_profile, planting_mmdd: scenario.planting_mmdd,
      daily_max_mm: scenario.daily_max_mm, seasonal_budget_mm: scenario.seasonal_budget_mm, observation_budget: scenario.observation_budget,
      sensor_noise_m3m3: scenario.sensor_noise_m3m3, sensor_mode: scenario.sensor_mode as ScenarioForm['sensor_mode'], initial_fraction_mean: scenario.initial_fraction_mean,
      dataset_id: scenario.dataset_id,
    } : {
      name: 'Kharif maize season', latitude: 10.79, longitude: 78.7, soil_profile: 'sandy_loam', planting_mmdd: '06-15', daily_max_mm: 20, seasonal_budget_mm: 350,
      observation_budget: 10, sensor_noise_m3m3: 0.02, sensor_mode: 'nominal', initial_fraction_mean: 0.7, dataset_id: sample?.id ?? null,
    },
  });
  const submit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      const saved = scenario ? await mutations.updateScenario({ id: scenario.id, ...values }) : await mutations.createScenario({ projectId, ...values });
      refresh('scenarios', 'scenario', 'seasons');
      ws.select(projectId, saved.id);
      onOpenChange(false);
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  const err = form.formState.errors;
  const reg = (name: keyof ScenarioForm) => ({ id: `s-${name}`, 'aria-invalid': !!err[name], 'aria-describedby': err[name] ? `s-${name}-error` : undefined, ...form.register(name) });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{scenario ? 'Edit field scenario' : 'New field scenario'}</DialogTitle>
          <DialogDescription>Location, soil, planting date, hard water limits and the soil-reading budget. Validated on the server; invalid crop/soil combinations are rejected with details.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2" noValidate>
          <div className="sm:col-span-2"><Field label="Scenario name" htmlFor="s-name" error={err.name?.message}><Input {...reg('name')} /></Field></div>
          <Field label="Latitude (°)" htmlFor="s-latitude" error={err.latitude?.message}><Input type="number" step="0.0001" {...reg('latitude')} /></Field>
          <Field label="Longitude (°)" htmlFor="s-longitude" error={err.longitude?.message}><Input type="number" step="0.0001" {...reg('longitude')} /></Field>
          <Field label="Soil profile" htmlFor="s-soil_profile" hint={defaults.data ? `θ WP/FC/SAT: ${['theta_wp', 'theta_fc', 'theta_sat'].map((k) => (defaults.data!.soils[form.watch('soil_profile')] as unknown as Record<string, number>)?.[k]).join(' / ')} m³/m³` : undefined}>
            <Select {...reg('soil_profile')}>{Object.keys(defaults.data?.soils ?? { sandy_loam: 1 }).map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}</Select>
          </Field>
          <Field label="Planting date (MM-DD)" htmlFor="s-planting_mmdd" error={err.planting_mmdd?.message} hint="Season length comes from the crop calendar (maize: 140 days)."><Input {...reg('planting_mmdd')} /></Field>
          <Field label="Max daily irrigation (mm/day)" htmlFor="s-daily_max_mm" error={err.daily_max_mm?.message}><Input type="number" step="1" {...reg('daily_max_mm')} /></Field>
          <Field label="Seasonal water budget (mm)" htmlFor="s-seasonal_budget_mm" error={err.seasonal_budget_mm?.message}><Input type="number" step="10" {...reg('seasonal_budget_mm')} /></Field>
          <Field label={<Term id="budget">Soil readings per season</Term>} htmlFor="s-observation_budget" error={err.observation_budget?.message}><Input type="number" step="1" {...reg('observation_budget')} /></Field>
          <Field label="Sensor noise σ (m³/m³)" htmlFor="s-sensor_noise_m3m3" error={err.sensor_noise_m3m3?.message}><Input type="number" step="0.005" {...reg('sensor_noise_m3m3')} /></Field>
          <Field label="Sensor scenario" htmlFor="s-sensor_mode" hint="Simulated faults for robustness tests.">
            <Select {...reg('sensor_mode')}>{['nominal', 'missing', 'biased', 'stuck', 'delayed'].map((m) => <option key={m} value={m}>{m}</option>)}</Select>
          </Field>
          <Field label="Initial wetness (fraction of TAW)" htmlFor="s-initial_fraction_mean" error={err.initial_fraction_mean?.message}><Input type="number" step="0.05" {...reg('initial_fraction_mean')} /></Field>
          <div className="sm:col-span-2">
            <Field label="Weather dataset" htmlFor="s-dataset_id" hint="Import or fetch more datasets in the Weather & Data Studio.">
              <Select id="s-dataset_id" value={form.watch('dataset_id') ?? ''} onChange={(e) => form.setValue('dataset_id', e.target.value || null)}>
                <option value="">— none —</option>
                {datasets.data?.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.start} → {d.end}){d.is_synthetic ? ' · synthetic' : ''}</option>)}
              </Select>
            </Field>
          </div>
          {error && <p role="alert" className="text-sm text-destructive sm:col-span-2">{error}</p>}
          <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={form.formState.isSubmitting}>{scenario ? 'Save scenario' : 'Create scenario'}</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function ProjectsPage() {
  const ws = useWorkspace();
  const [params, setParams] = useSearchParams();
  const [showArchived, setShowArchived] = React.useState(false);
  const projects = useProjects(showArchived);
  const [selected, setSelected] = React.useState<string | null>(null);
  const projectId = selected ?? ws.projectId;
  const scenarios = useScenarios(projectId, showArchived);
  const [projectDialog, setProjectDialog] = React.useState<{ open: boolean; project?: Project }>({ open: params.get('new') === '1' });
  const [scenarioDialog, setScenarioDialog] = React.useState<{ open: boolean; scenario?: Scenario }>({ open: false });
  const refresh = useInvalidate();
  const [busy, setBusy] = React.useState(false);
  const project = projects.data?.find((p) => p.id === projectId);

  const sample = async () => {
    setBusy(true);
    try {
      const res = await mutations.sampleProject();
      ws.select(res.project.id, res.scenario.id);
      setSelected(res.project.id);
      refresh('projects', 'scenarios');
    } finally {
      setBusy(false);
    }
  };
  const setArchived = async (p: Project, archived: boolean) => {
    await mutations.updateProject({ id: p.id, archived });
    refresh('projects');
  };
  const setScenarioArchived = async (s: Scenario, archived: boolean) => {
    await mutations.updateScenario({ id: s.id, archived });
    refresh('scenarios');
  };

  return (
    <>
      <PageHeader title="Projects & Fields" description="Create, edit and archive field projects and their season scenarios. Archiving keeps all runs and artifacts for reproducibility."
        actions={<>
          <Button variant="outline" onClick={sample} disabled={busy}><TestTube2 aria-hidden />Sample field</Button>
          <Button onClick={() => setProjectDialog({ open: true })}><Plus aria-hidden />New project</Button>
        </>} />
      <div className="mb-4 flex items-center gap-2 text-sm">
        <Switch id="show-archived" checked={showArchived} onCheckedChange={setShowArchived} />
        <label htmlFor="show-archived">Show archived</label>
      </div>
      {projects.isError && <ErrorPanel error={projects.error} retry={() => projects.refetch()} />}
      {projects.isLoading ? <LoadingBlock /> : !projects.data?.length ? (
        <EmptyState icon={Sprout} title="No field projects yet" description="Start with the synthetic sample field or create your own."
          action={<><Button variant="outline" onClick={sample} disabled={busy}>Explore sample field</Button><Button onClick={() => setProjectDialog({ open: true })}>Create my field</Button></>} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,340px)_1fr]">
          <Card>
            <CardHeader><CardTitle>Projects</CardTitle></CardHeader>
            <CardContent className="flex flex-col gap-1.5">
              {projects.data.map((p) => (
                <div key={p.id} className={cn('flex items-center gap-2 rounded-md border p-2.5', p.id === projectId && 'border-primary bg-secondary')}>
                  <button type="button" className="min-w-0 flex-1 text-left" onClick={() => { setSelected(p.id); ws.select(p.id); setParams({}); }} aria-pressed={p.id === projectId}>
                    <span className="block truncate text-sm font-medium">{p.name}</span>
                    <span className="flex flex-wrap gap-1 pt-1">
                      {p.is_sample && <Badge variant="warning">synthetic sample</Badge>}
                      {p.archived && <Badge variant="outline">archived</Badge>}
                      <Badge variant="outline">{p.scenario_count ?? 0} scenario(s)</Badge>
                    </span>
                  </button>
                  <Button variant="ghost" size="icon" aria-label={`Edit ${p.name}`} onClick={() => setProjectDialog({ open: true, project: p })}><Pencil /></Button>
                  <Button variant="ghost" size="icon" aria-label={p.archived ? `Restore ${p.name}` : `Archive ${p.name}`} onClick={() => setArchived(p, !p.archived)}>{p.archived ? <ArchiveRestore /> : <Archive />}</Button>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex-row items-start justify-between gap-2">
              <div><CardTitle>{project?.name ?? 'Select a project'}</CardTitle><CardDescription>{project?.description || 'Field scenarios'}</CardDescription></div>
              {project && !project.archived && <Button size="sm" onClick={() => setScenarioDialog({ open: true })}><Plus aria-hidden />New scenario</Button>}
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {scenarios.isLoading ? <LoadingBlock rows={2} /> : !scenarios.data?.length ? (
                <EmptyState title="No scenarios" description="A scenario defines one season's crop, soil, water budget and observation budget." />
              ) : scenarios.data.map((s) => (
                <div key={s.id} className={cn('rounded-lg border p-4', s.id === ws.scenarioId && 'border-primary')}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <h3 className="font-semibold">{s.name}</h3>
                      <p className="text-xs text-muted-foreground">{s.latitude.toFixed(2)}°, {s.longitude.toFixed(2)}° · {s.crop_profile} · {s.soil_profile.replace('_', ' ')} · planting {s.planting_mmdd} · {s.season_length_days ?? '—'} days</p>
                    </div>
                    <div className="flex gap-1">
                      {s.id === ws.scenarioId ? <Badge variant="success"><CheckCircle2 />active</Badge> : <Button size="sm" variant="outline" onClick={() => ws.select(s.project_id, s.id)}>Set active</Button>}
                      <Button size="icon" variant="ghost" aria-label={`Edit ${s.name}`} onClick={() => setScenarioDialog({ open: true, scenario: s })}><Pencil /></Button>
                      <Button size="icon" variant="ghost" aria-label={s.archived ? `Restore ${s.name}` : `Archive ${s.name}`} onClick={() => setScenarioArchived(s, !s.archived)}>{s.archived ? <ArchiveRestore /> : <Archive />}</Button>
                    </div>
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
                    <div><dt className="text-xs text-muted-foreground">Daily cap</dt><dd className="tabular">{s.daily_max_mm} mm/day</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Seasonal water</dt><dd className="tabular">{s.seasonal_budget_mm} mm</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Soil readings</dt><dd className="tabular">{s.observation_budget}</dd></div>
                    <div><dt className="text-xs text-muted-foreground">Sensor</dt><dd className="tabular">σ {s.sensor_noise_m3m3} m³/m³ · {s.sensor_mode}</dd></div>
                  </dl>
                  {s.config_error && <Notice tone="warning" className="mt-3">Configuration error: {s.config_error}</Notice>}
                  {s.validation_messages.length > 0 && (
                    <Notice tone={s.validation_status === 'valid' ? 'info' : 'warning'} className="mt-3">{s.validation_messages.join(' · ')}</Notice>
                  )}
                  {s.scenario_sha256 && <p className="mt-2 font-mono text-[11px] text-muted-foreground">config sha256 {s.scenario_sha256.slice(0, 16)}…</p>}
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
      <ProjectDialog open={projectDialog.open} project={projectDialog.project} onOpenChange={(o) => { setProjectDialog({ open: o }); if (!o) setParams({}); }} />
      {projectId && <ScenarioDialog open={scenarioDialog.open} scenario={scenarioDialog.scenario} projectId={projectId} onOpenChange={(o) => setScenarioDialog({ open: o })} />}
    </>
  );
}
