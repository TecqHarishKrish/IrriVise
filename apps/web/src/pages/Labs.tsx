import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BarChart, Bar, ScatterChart, Scatter, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Play, Beaker, Shield, CheckCircle2 } from 'lucide-react';
import { Panel, ErrorBox, Empty, StatusBadge, CancelButton, ProgressBar, ChartLegendLabel } from '../components/ui';
import { CHART_COLORS, tooltipStyle } from '../chartConfig';
import { api } from '../api';
import { useExperiments } from '../hooks/useData';
import type { DataReturn, Scenario, ModelRecord, Job, Project, Dataset, Run } from '../types';

// ─── Training ─────────────────────────────────────────────────────────────────
export function Training({ data }: { data: DataReturn }) {
  const qc = useQueryClient();
  const [projectId, setProjectId] = useState('');
  const [scenarioId, setScenarioId] = useState('');
  const [seed, setSeed] = useState(42);
  const [timesteps, setTimesteps] = useState(2048);

  const actualProject = projectId || data.projects.data?.[0]?.id || '';
  const scenarios = useQuery({
    queryKey: ['scenarios', actualProject],
    queryFn: () => api<Scenario[]>(`/api/v1/projects/${actualProject}/scenarios`),
    enabled: !!actualProject,
  });
  const chosen = scenarioId || scenarios.data?.[0]?.id || '';

  const models = useQuery({
    queryKey: ['models'],
    queryFn: () => api<ModelRecord[]>('/api/v1/models'),
    refetchInterval: 4000,
  });

  const enqueue = useMutation({
    mutationFn: () => api<{ job_id: string }>('/api/v1/training', {
      method: 'POST',
      body: JSON.stringify({ scenario_id: chosen, preset: 'cpu_quick', seed, total_timesteps: timesteps }),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  });

  const trainingJobs = data.jobs.data?.filter((j: Job) => j.kind === 'training') || [];

  const PRESETS = [
    { label: 'Quick smoke',    steps: 2048,  desc: 'Functional test only — not research quality', color: CHART_COLORS.stress },
    { label: 'Standard CPU',  steps: 10000, desc: '~10k steps — better policy signal',            color: CHART_COLORS.irrigation },
    { label: 'Extended CPU',  steps: 50000, desc: '~50k steps — more stable training',             color: CHART_COLORS.ppo },
  ];

  return (
    <div className="grid two">
      <Panel title="PPO training">
        <p className="muted">
          Trains a real Stable-Baselines3 PPO policy on synthetic seasons.
          This verifies training, checkpoint save/load, and inference work — it does not validate field irrigation performance.
        </p>
        <label>Project
          <select value={actualProject} onChange={e => { setProjectId(e.target.value); setScenarioId(''); }}>
            {data.projects.data?.map((p: Project) => <option value={p.id} key={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label>Scenario
          <select value={chosen} onChange={e => setScenarioId(e.target.value)}>
            {scenarios.data?.map(s => <option value={s.id} key={s.id}>{s.name} · {s.budget_mm} mm</option>)}
          </select>
        </label>
        <div className="form-grid">
          <label>Seed (0–2B)
            <input type="number" min="0" max="2147483647" value={seed} onChange={e => setSeed(Number(e.target.value))} />
          </label>
          <label>Timesteps
            <input type="number" min="256" max="10000" step="256" value={timesteps} onChange={e => setTimesteps(Number(e.target.value))} />
          </label>
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
          {PRESETS.map(p => (
            <button key={p.label} className="ghost" title={p.desc}
              style={{ borderColor: p.color, fontSize: 11 }}
              onClick={() => setTimesteps(p.steps)}>
              {p.label} ({p.steps.toLocaleString()})
            </button>
          ))}
        </div>
        <button
          className="button"
          disabled={!chosen || enqueue.isPending || trainingJobs.some((j: Job) => j.status === 'running' || j.status === 'queued')}
          onClick={() => enqueue.mutate()}
        >
          <Play size={15} />{enqueue.isPending ? 'Queueing…' : 'Queue PPO training'}
        </button>
        {enqueue.isError && <ErrorBox message={String(enqueue.error)} />}
        <p className="note">Only one worker job runs at a time. Cancellation is polled every 32 steps.</p>
      </Panel>

      <Panel title="Training jobs">
        {trainingJobs.length ? (
          <>
            {trainingJobs.filter((j: Job) => j.status === 'running').map((j: Job) => (
              <div key={j.id} style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 12 }}>
                  <span><b>PPO · seed {j.seed}</b></span>
                  <span style={{ color: 'var(--muted)' }}>{j.current_step.toLocaleString()} / {j.total_steps.toLocaleString()} steps</span>
                </div>
                <ProgressBar pct={j.progress} />
              </div>
            ))}
            <div className="list">
              {trainingJobs.slice(0, 8).map((job: Job) => (
                <div className="list-item" key={job.id}>
                  <StatusBadge status={job.status} />
                  <span>
                    <b>PPO · seed {job.seed}</b>
                    <small>{job.current_step.toLocaleString()} / {job.total_steps.toLocaleString()} steps · {job.id.slice(0, 8)}</small>
                  </span>
                  {(job.status === 'queued' || job.status === 'running') && <CancelButton id={job.id} />}
                  {job.error && <small style={{ color: '#a4492d' }}>{job.error.slice(0, 80)}</small>}
                </div>
              ))}
            </div>
          </>
        ) : <Empty text="No training jobs yet. Queue the CPU quick preset." icon={<Beaker size={28} />} />}
      </Panel>

      <Panel title="Verified checkpoints" className="span-two">
        {models.data?.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Algorithm</th><th>Seed</th><th>Actual steps</th>
                    <th>Checkpoint SHA-256</th><th>Evaluation</th><th>Research quality</th>
                  </tr>
                </thead>
                <tbody>
                  {models.data.map(m => (
                    <tr key={m.checkpoint}>
                      <td>{m.algorithm}</td>
                      <td>{m.seed}</td>
                      <td>{m.actual_timesteps.toLocaleString()}</td>
                      <td><code style={{ fontSize: 10 }}>{m.checkpoint_sha256?.slice(0, 16) || '—'}…</code></td>
                      <td>{m.evaluation}</td>
                      <td>
                        {m.research_quality
                          ? <span style={{ color: CHART_COLORS.voi, display: 'flex', alignItems: 'center', gap: 4 }}><CheckCircle2 size={12} /> Yes</span>
                          : <span style={{ color: 'var(--muted)' }}>No — functional test only</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="note">A verified checkpoint passes save/load and one-step inference. Research quality requires held-out evaluation.</p>
          </>
        ) : <Empty text="No verified checkpoint. A model appears after save/load and inference succeed." icon={<Shield size={28} />} />}
      </Panel>
    </div>
  );
}

// ─── Experiments ──────────────────────────────────────────────────────────────
export function Experiments({ data }: { data: DataReturn }) {
  const qc = useQueryClient();
  const [projectId, setProjectId] = useState('');
  const [scenarioId, setScenarioId] = useState('');
  const [datasetId, setDatasetId] = useState('sample');
  const [seed, setSeed] = useState(42);
  const [selectedControllers, setSelectedControllers] = useState<string[]>(['fixed', 'threshold', 'carat']);

  const actualProject = projectId || data.projects.data?.[0]?.id || '';
  const scenarios = useQuery({
    queryKey: ['scenarios', actualProject],
    queryFn: () => api<Scenario[]>(`/api/v1/projects/${actualProject}/scenarios`),
    enabled: !!actualProject,
  });
  const chosen = scenarioId || scenarios.data?.[0]?.id || '';
  const experiments = useExperiments();

  const enqueue = useMutation({
    mutationFn: () => api<{ experiment_id: string; job_ids: string[] }>('/api/v1/experiments', {
      method: 'POST',
      body: JSON.stringify({ scenario_id: chosen, dataset_id: datasetId, seed, controllers: selectedControllers }),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['experiments'] });
    },
  });

  const ALL_CONTROLLERS = [
    { id: 'fixed',        label: 'B0: Fixed interval',        desc: '10 mm every 3 days' },
    { id: 'threshold',    label: 'B1: Moisture threshold',    desc: 'Refill at 80% FC' },
    { id: 'deficit',      label: 'B2: Deficit irrigation',    desc: 'Lower threshold, budget-aware' },
    { id: 'conservative', label: 'B3: Conservative threshold', desc: 'High reserve, stress-sensitive' },
    { id: 'carat',        label: 'P: CARAT prototype',        desc: 'Full CARAT with observation budget' },
  ];

  const toggleController = (id: string) =>
    setSelectedControllers(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]);

  const latestExp = experiments.data?.find(e => (e.status === 'complete' || e.status === 'succeeded') && e.results.length > 0);
  const compData = latestExp?.results.map(r => ({
    name: r.controller,
    irrigation: +r.seasonal_irrigation_mm.toFixed(1),
    yield_val: +(r.aquacrop_simulated_dry_yield_t_ha ?? r.yield_proxy_t_ha).toFixed(2),
    stress: +r.cumulative_stress_proxy.toFixed(2),
    observations: r.observations_used,
  })) || [];

  return (
    <>
      <Panel title="Matched benchmark experiment">
        <p className="muted">
          Run multiple controllers on the <strong>same</strong> scenario, seed, and weather.
          This is not yet a multi-seed statistical benchmark — matched multi-seed experiments with CIs remain future work.
        </p>
        <div className="grid two" style={{ gap: 16 }}>
          <div>
            <label>Project
              <select value={actualProject} onChange={e => { setProjectId(e.target.value); setScenarioId(''); }}>
                {data.projects.data?.map((p: Project) => <option value={p.id} key={p.id}>{p.name}</option>)}
              </select>
            </label>
            <label>Scenario
              <select value={chosen} onChange={e => setScenarioId(e.target.value)}>
                {scenarios.data?.map(s => <option value={s.id} key={s.id}>{s.name}</option>)}
              </select>
            </label>
            <div className="form-grid">
              <label>Weather
                <select value={datasetId} onChange={e => setDatasetId(e.target.value)}>
                  {data.datasets.data?.map((d: Dataset) => (
                    <option value={d.id} key={d.id}>
                      {d.source === 'nasa_power' ? 'NASA POWER' : 'Synthetic'} · {d.days} days
                    </option>
                  ))}
                </select>
              </label>
              <label>Shared seed
                <input type="number" min="0" max="2147483647" value={seed} onChange={e => setSeed(Number(e.target.value))} />
              </label>
            </div>
          </div>
          <div>
            <p style={{ fontSize: 11, fontWeight: 800, color: 'var(--muted)', margin: '0 0 10px' }}>Select controllers to compare</p>
            {ALL_CONTROLLERS.map(c => (
              <label
                key={c.id}
                className={`controller-card ${selectedControllers.includes(c.id) ? 'selected' : ''}`}
                style={{ marginBottom: 6, cursor: 'pointer' }}
              >
                <input type="checkbox" style={{ width: 'auto', minHeight: 'auto' }}
                  checked={selectedControllers.includes(c.id)} onChange={() => toggleController(c.id)} />
                <span><b>{c.label}</b><small>{c.desc}</small></span>
              </label>
            ))}
          </div>
        </div>
        <button
          className="button" style={{ marginTop: 8 }}
          disabled={!chosen || selectedControllers.length < 2 || enqueue.isPending}
          onClick={() => enqueue.mutate()}
        >
          <Play size={15} />{enqueue.isPending ? 'Queueing…' : `Run ${selectedControllers.length} controllers`}
        </button>
        {selectedControllers.length < 2 && <p className="note">Select at least 2 controllers.</p>}
        {enqueue.isError && <ErrorBox message={String(enqueue.error)} />}
        {enqueue.data && (
          <p className="note" style={{ color: CHART_COLORS.voi }}>
            Queued {enqueue.data.job_ids.length} jobs · experiment {enqueue.data.experiment_id.slice(0, 8)}
          </p>
        )}
      </Panel>

      {compData.length > 0 && (
        <Panel title={`Latest experiment · ${latestExp!.controllers.join(', ')} · seed ${latestExp!.seed}`}>
          <p className="muted">All controllers: same scenario, seed, weather. One synthetic scenario — not a multi-seed evaluation.</p>
          <div style={{ display: 'flex', gap: 16, marginBottom: 8, flexWrap: 'wrap' }}>
            <ChartLegendLabel color={CHART_COLORS.irrigation} label="Seasonal irrigation (mm)" />
            <ChartLegendLabel color={CHART_COLORS.stress} label="Cumulative stress proxy" />
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={compData} margin={{ top: 10, right: 20, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--muted)' }} />
              <YAxis yAxisId="left" tick={{ fontSize: 10, fill: 'var(--muted)' }} unit=" mm" />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: 'var(--muted)' }} />
              <Tooltip {...tooltipStyle} />
              <Bar yAxisId="left" dataKey="irrigation" fill={CHART_COLORS.irrigation} radius={[4,4,0,0]} name="Irrigation (mm)" />
              <Bar yAxisId="right" dataKey="stress" fill={CHART_COLORS.stress} radius={[4,4,0,0]} name="Stress proxy" />
            </BarChart>
          </ResponsiveContainer>
          <div className="table-wrap" style={{ marginTop: 20 }}>
            <table>
              <thead>
                <tr>
                  <th>Controller</th><th>Irrigation · mm</th><th>Yield · t/ha</th>
                  <th>Stress · sum</th><th>Readings</th><th>Water savings vs fixed</th>
                </tr>
              </thead>
              <tbody>
                {latestExp!.results.map(r => {
                  const fixed = latestExp!.results.find(x => x.controller === 'fixed');
                  const savings = fixed && fixed.seasonal_irrigation_mm > 0
                    ? ((fixed.seasonal_irrigation_mm - r.seasonal_irrigation_mm) / fixed.seasonal_irrigation_mm * 100).toFixed(1)
                    : null;
                  return (
                    <tr key={r.controller}>
                      <td><b>{r.controller}</b></td>
                      <td>{r.seasonal_irrigation_mm.toFixed(1)}</td>
                      <td>{r.aquacrop_simulated_dry_yield_t_ha?.toFixed(2) ?? `${r.yield_proxy_t_ha.toFixed(2)} (proxy)`}</td>
                      <td>{r.cumulative_stress_proxy.toFixed(2)}</td>
                      <td>{r.observations_used}</td>
                      <td>{savings !== null ? `${savings}%` : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="note">Water savings vs fixed baseline. One seed, one scenario — descriptive only, not statistically validated.</p>
        </Panel>
      )}

      {experiments.data && experiments.data.length > 0 && (
        <Panel title="Experiment history">
          <div className="list">
            {experiments.data.slice(0, 10).map(exp => (
              <div className="list-item" key={exp.id}>
                <StatusBadge status={exp.status === 'complete' || exp.status === 'succeeded' ? 'succeeded' : exp.status === 'partial' ? 'running' : 'queued'} />
                <span>
                  <b>{exp.controllers.join(' vs ')} · seed {exp.seed}</b>
                  <small>{new Date(exp.created_at).toLocaleString()} · {exp.results.length}/{exp.controllers.length} completed</small>
                </span>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="Ablation plan (future work)">
        <p className="muted">The master specification defines seven ablation configurations requiring held-out test seasons.</p>
        <div className="table-wrap">
          <table>
            <thead><tr><th>#</th><th>Configuration</th><th>Status</th></tr></thead>
            <tbody>
              {[
                ['1', 'PPO — no CARAT',                                     'baseline runs available'],
                ['2', 'PPO + fixed-interval observation',                   'pending'],
                ['3', 'PPO + random observation (matched budget)',            'pending'],
                ['4', 'PPO + uncertainty-threshold observation',             'pending'],
                ['5', 'PPO + counterfactual regret, no risk manager',       'pending'],
                ['6', 'PPO + CARAT, no belief correction',                  'pending'],
                ['7', 'Full CARAT + twin correction + risk manager',        'carat runs available'],
              ].map(([n, label, status]) => (
                <tr key={n}>
                  <td>{n}</td><td>{label}</td>
                  <td style={{ color: status.includes('pending') ? 'var(--muted)' : CHART_COLORS.voi }}>{status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

// ─── Analytics ────────────────────────────────────────────────────────────────
import { useMutation as useMut } from '@tanstack/react-query';
import { FlaskConical as Flask } from 'lucide-react';

export function Analytics({ data }: { data: DataReturn }) {
  const runs = data.runs.data || [];
  const [runId, setRunId] = useState(runs[0]?.id || '');
  const [question, setQuestion] = useState('Summarise the water use, stress signal, and twin accuracy for this run.');

  const brief = useMut({
    mutationFn: () => api<{ provider: string; model: string; text: string }>('/api/v1/analyst/brief', {
      method: 'POST',
      body: JSON.stringify({ run_id: runId, question }),
    }),
  });

  const compData = runs.slice(0, 12).map((r: Run) => ({
    name: r.controller,
    irrigation: +r.summary.seasonal_irrigation_mm.toFixed(1),
    yield_val: +(r.summary.aquacrop?.aquacrop_simulated_dry_yield_t_ha ?? r.summary.yield_proxy_t_ha).toFixed(2),
    stress: +r.summary.cumulative_stress_proxy.toFixed(2),
    rmse: +r.summary.twin_rmse_mm.toFixed(1),
    observations: r.summary.observations_used,
  }));

  const SCATTER_COLORS: Record<string, string> = {
    carat: CHART_COLORS.reference,
    fixed: CHART_COLORS.stress,
    threshold: CHART_COLORS.irrigation,
    deficit: CHART_COLORS.rain,
    conservative: '#7c5cbf',
  };

  return (
    <>
      <Panel title="Simulation outcomes — all saved runs">
        {runs.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Controller</th><th>Irrigation · mm</th><th>AquaCrop yield · t/ha</th>
                    <th>Yield proxy · t/ha</th><th>Stress · sum</th><th>Twin RMSE · mm</th><th>Readings</th><th>Days</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r: Run) => (
                    <tr key={r.id}>
                      <td><b>{r.controller}</b></td>
                      <td>{r.summary.seasonal_irrigation_mm.toFixed(1)}</td>
                      <td>{r.summary.aquacrop?.aquacrop_simulated_dry_yield_t_ha.toFixed(2) ?? '—'}</td>
                      <td style={{ color: 'var(--muted)' }}>{r.summary.yield_proxy_t_ha.toFixed(2)}</td>
                      <td>{r.summary.cumulative_stress_proxy.toFixed(2)}</td>
                      <td>{r.summary.twin_rmse_mm.toFixed(1)}</td>
                      <td>{r.summary.observations_used}</td>
                      <td>{r.summary.days}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="note">Runs may use different scenarios and weather — not a matched benchmark. Use Experiment Benchmark for controlled comparisons.</p>
          </>
        ) : <Empty text="No simulation data yet." />}
      </Panel>

      {compData.length >= 2 && (
        <>
          <Panel title="Irrigation vs simulated yield (each point = one run)">
            <p className="muted">
              Lower x = more water-efficient. Higher y = better simulated yield.
              Colours: green = threshold, orange = CARAT, amber = fixed, blue = deficit, purple = conservative.
            </p>
            <ResponsiveContainer width="100%" height={260}>
              <ScatterChart margin={{ top: 10, right: 30, bottom: 30, left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                <XAxis dataKey="irrigation" name="Irrigation (mm)" type="number"
                  tick={{ fontSize: 10, fill: 'var(--muted)' }} unit=" mm"
                  label={{ value: 'Seasonal irrigation (mm)', position: 'insideBottom', offset: -14, fontSize: 10, fill: 'var(--muted)' }} />
                <YAxis dataKey="yield_val" name="Yield (t/ha)" type="number"
                  tick={{ fontSize: 10, fill: 'var(--muted)' }} unit=" t/ha"
                  label={{ value: 'Yield (t/ha)', angle: -90, position: 'insideLeft', fontSize: 10, fill: 'var(--muted)' }} />
                <Tooltip {...tooltipStyle} cursor={{ strokeDasharray: '3 3' }}
                  content={({ payload }) => {
                    if (!payload?.length) return null;
                    const d = payload[0].payload;
                    return (
                      <div style={{ ...tooltipStyle.contentStyle, padding: '10px 14px' }}>
                        <p style={{ ...tooltipStyle.labelStyle, margin: '0 0 6px' }}>{d.name}</p>
                        <p style={{ margin: '2px 0', fontSize: 11, color: 'var(--text)' }}>Irrigation: {d.irrigation} mm</p>
                        <p style={{ margin: '2px 0', fontSize: 11, color: 'var(--text)' }}>Yield: {d.yield_val} t/ha</p>
                        <p style={{ margin: '2px 0', fontSize: 11, color: 'var(--muted)' }}>Stress: {d.stress} · Obs: {d.observations}</p>
                      </div>
                    );
                  }}
                />
                <Scatter name="Runs" data={compData} fill={CHART_COLORS.irrigation}>
                  {compData.map((entry: { name: string }, i: number) => (
                    <Cell key={i} fill={SCATTER_COLORS[entry.name] ?? CHART_COLORS.irrigation} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </Panel>

          <Panel title="Digital twin estimation error by run">
            <p className="muted">RMSE of estimated vs hidden reference storage. Lower = twin tracked reference more closely.</p>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={compData} margin={{ top: 5, right: 20, bottom: 20, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--muted)' }} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--muted)' }} unit=" mm" />
                <Tooltip {...tooltipStyle} />
                <Bar dataKey="rmse" fill="#7c5cbf" radius={[4,4,0,0]} name="Twin RMSE (mm)" />
              </BarChart>
            </ResponsiveContainer>
          </Panel>
        </>
      )}

      <Panel title="AI analyst brief">
        <p className="muted">An optional language model explains a saved simulation run using its summary and recent trace.</p>
        {runs.length ? (
          <>
            <label>Saved run
              <select value={runId} onChange={e => setRunId(e.target.value)}>
                {runs.map((r: Run) => <option value={r.id} key={r.id}>{r.controller} · {new Date(r.created_at).toLocaleString()}</option>)}
              </select>
            </label>
            <label>Question
              <input value={question} maxLength={1000} onChange={e => setQuestion(e.target.value)} />
            </label>
            <button className="button" disabled={brief.isPending} onClick={() => brief.mutate()}>
              <Flask size={15} />{brief.isPending ? 'Analysing…' : 'Generate evidence brief'}
            </button>
            {brief.isError && <ErrorBox message="Analyst temporarily unavailable. Check server configuration." />}
            {brief.data && (
              <div className="analyst-answer">
                <small>{brief.data.provider} · {brief.data.model}</small>
                <p>{brief.data.text}</p>
              </div>
            )}
          </>
        ) : <Empty text="Run a simulation first. The analyst only explains saved run evidence." />}
      </Panel>
    </>
  );
}
