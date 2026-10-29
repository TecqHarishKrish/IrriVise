import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { CloudSun, Play, Droplets, Eye, EyeOff, RefreshCw } from 'lucide-react';
import { Panel, ErrorBox, Empty, StatusBadge, CancelButton, ChartLegendLabel } from '../components/ui';
import { CHART_COLORS, tooltipStyle } from '../chartConfig';
import { api } from '../api';
import { useDaily } from '../hooks/useData';
import type { DataReturn, Scenario, Job, Dataset, Run, Project } from '../types';

// ─── Data Studio ──────────────────────────────────────────────────────────────
export function DataPage({ data }: { data: DataReturn }) {
  const qc = useQueryClient();
  const [projectId, setProjectId] = useState('');
  const [scenarioId, setScenarioId] = useState('');
  const [latitude, setLatitude] = useState(10.79);
  const [longitude, setLongitude] = useState(78.7);
  const [start, setStart] = useState('2024-01-01');
  const [end, setEnd] = useState('2024-05-29');
  const [timeStandard, setTimeStandard] = useState('UTC');
  const [previewId, setPreviewId] = useState<string | null>(null);

  const actualProject = projectId || data.projects.data?.[0]?.id || '';
  const scenarios = useQuery({
    queryKey: ['scenarios', actualProject],
    queryFn: () => api<Scenario[]>(`/api/v1/projects/${actualProject}/scenarios`),
    enabled: !!actualProject,
  });
  const chosen = scenarioId || scenarios.data?.[0]?.id || '';

  const preview = useQuery({
    queryKey: ['preview', previewId],
    queryFn: () => api<Record<string, unknown>[]>(`/api/v1/datasets/${previewId}/preview`),
    enabled: !!previewId,
  });

  const fetchWeather = useMutation({
    mutationFn: () => api<{ job_id: string }>('/api/v1/datasets/nasa-power', {
      method: 'POST',
      body: JSON.stringify({ scenario_id: chosen, latitude, longitude, start, end, time_standard: timeStandard }),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['datasets'] });
    },
  });

  const weatherJobs = data.jobs.data?.filter((j: Job) => j.kind === 'weather') || [];

  return (
    <div className="grid two">
      <Panel
        title="Available weather datasets"
        action={<button className="ghost" onClick={() => qc.invalidateQueries({ queryKey: ['datasets'] })}><RefreshCw size={13} /></button>}
      >
        <p className="muted">
          The offline fixture is seeded synthetic data. NASA POWER records are historical gridded weather — not farm measurements.
          Reference ET₀ uses FAO-56 Penman-Monteith.
        </p>
        {data.datasets.isLoading && <p style={{ color: 'var(--muted)', fontSize: 13 }}>Loading…</p>}
        {data.datasets.data?.map((d: Dataset) => (
          <div className="dataset" key={d.id}>
            <div className="icon-disc"><CloudSun size={22} /></div>
            <div style={{ flex: 1 }}>
              <h3 style={{ marginBottom: 4 }}>
                {d.source === 'nasa_power' ? 'NASA POWER historical' : 'Synthetic demonstration'}
              </h3>
              <p>{d.days} days · {d.start} to {d.end}</p>
              <small>SHA-256 {d.checksum_sha256.slice(0, 20)}…</small>
            </div>
            <button className="ghost" onClick={() => setPreviewId(previewId === d.id ? null : d.id)}>
              {previewId === d.id ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        ))}
        {!data.datasets.data?.length && !data.datasets.isLoading && (
          <Empty text="No datasets. The synthetic sample appears after the first successful run." />
        )}
        {previewId && preview.data && (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>{Object.keys(preview.data[0] || {}).map(k => <th key={k}>{k}</th>)}</tr>
              </thead>
              <tbody>
                {preview.data.map((row, i) => (
                  <tr key={i}>
                    {Object.values(row).map((v, j) => (
                      <td key={j}>{typeof v === 'number' ? v.toFixed(3) : String(v)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Fetch NASA POWER daily weather">
        <p className="muted">A background worker downloads the selected historical date range. Repeated identical requests use the local cache.</p>
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
          <label>Latitude<input type="number" min="-90" max="90" step="0.01" value={latitude} onChange={e => setLatitude(Number(e.target.value))} /></label>
          <label>Longitude<input type="number" min="-180" max="180" step="0.01" value={longitude} onChange={e => setLongitude(Number(e.target.value))} /></label>
          <label>Start date<input type="date" value={start} onChange={e => setStart(e.target.value)} /></label>
          <label>End date<input type="date" value={end} onChange={e => setEnd(e.target.value)} /></label>
        </div>
        <label>POWER time standard
          <select value={timeStandard} onChange={e => setTimeStandard(e.target.value)}>
            <option value="UTC">UTC</option>
            <option value="LST">Local solar time (LST)</option>
          </select>
        </label>
        <button
          className="button"
          disabled={!chosen || fetchWeather.isPending || weatherJobs.some((j: Job) => j.status === 'queued' || j.status === 'running')}
          onClick={() => fetchWeather.mutate()}
        >
          <CloudSun size={15} />Queue historical fetch
        </button>
        {fetchWeather.isError && <ErrorBox message={String(fetchWeather.error)} />}
        <p className="note">Maximum 731 past days. UTC and LST do not automatically represent local civil time.</p>
      </Panel>

      <Panel title="Weather fetch jobs">
        {weatherJobs.length ? (
          <div className="list">
            {weatherJobs.slice(0, 6).map((j: Job) => (
              <div className="list-item" key={j.id}>
                <StatusBadge status={j.status} />
                <span>
                  <b>NASA POWER</b>
                  <small>{j.id.slice(0, 8)} · {j.error || 'Daily point request'}</small>
                </span>
                {(j.status === 'queued' || j.status === 'running') && <CancelButton id={j.id} />}
              </div>
            ))}
          </div>
        ) : <Empty text="No fetch jobs. The synthetic sample is available offline." />}
      </Panel>

      <Panel title="Data provenance">
        <dl className="facts">
          <dt>Sample source</dt><dd>Seeded synthetic generator — labeled demonstration only</dd>
          <dt>Historical source</dt><dd>NASA POWER daily point API; raw JSON cached locally</dd>
          <dt>Rain units</dt><dd>mm/day (PRECTOTCORR)</dd>
          <dt>Temperature units</dt><dd>°C (T2M_MAX, T2M_MIN)</dd>
          <dt>ET₀ calculation</dt><dd>FAO-56 Penman-Monteith; RH₂M mean approximation; NASA elevation</dd>
          <dt>Time standard</dt><dd>UTC or LST per request; not converted to civil time</dd>
          <dt>Split policy</dt><dd>Chronological whole-season splits (pending sufficient seasons)</dd>
        </dl>
        <p className="note">Historical runs still simulate a field — they are never measured farm outcomes.</p>
      </Panel>
    </div>
  );
}

// ─── Simulation ───────────────────────────────────────────────────────────────
export function Simulation({ data }: { data: DataReturn }) {
  const qc = useQueryClient();
  const [projectId, setProjectId] = useState('');
  const [scenarioId, setScenarioId] = useState('');
  const [controller, setController] = useState('threshold');
  const [datasetId, setDatasetId] = useState('sample');
  const [seed, setSeed] = useState(42);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);

  const actualProject = projectId || data.projects.data?.[0]?.id || '';
  const scenarios = useQuery({
    queryKey: ['scenarios', actualProject],
    queryFn: () => api<Scenario[]>(`/api/v1/projects/${actualProject}/scenarios`),
    enabled: !!actualProject,
  });
  const chosen = scenarioId || scenarios.data?.[0]?.id || '';

  const enqueue = useMutation({
    mutationFn: () => api<{ job_id: string }>('/api/v1/simulations', {
      method: 'POST',
      body: JSON.stringify({ scenario_id: chosen, controller, dataset_id: datasetId, seed }),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      qc.invalidateQueries({ queryKey: ['runs'] });
    },
  });

  const runForChart = selectedRun || data.runs.data?.[0]?.id;
  const daily = useDaily(runForChart ?? undefined);

  const chartData = daily.data?.map(d => ({
    day: d.day,
    rain: +d.rain_mm.toFixed(1),
    irrigation: +d.irrigation_mm.toFixed(1),
    storage: +d.estimated_storage_mm.toFixed(1),
    stress: +d.stress_proxy.toFixed(3),
  }));

  const CONTROLS = [
    { id: 'threshold',    label: 'Moisture threshold',      desc: 'Refill when root zone < 80% FC.',           color: CHART_COLORS.irrigation },
    { id: 'deficit',      label: 'Deficit irrigation',       desc: 'Lower threshold, budget-aware.',             color: CHART_COLORS.rain },
    { id: 'conservative', label: 'Stress-sensitive crop',    desc: 'High reserve, stress-sensitive stages.',     color: '#7c5cbf' },
    { id: 'fixed',        label: 'Fixed calendar baseline',  desc: '10 mm every 3 days — transparent B0.',       color: CHART_COLORS.stress },
    { id: 'carat',        label: 'CARAT research prototype', desc: 'Estimated VOI guides action & observation.', color: CHART_COLORS.reference },
  ];

  return (
    <div className="grid two">
      <Panel title="Run a season scenario">
        <p className="muted">Choose a field, season, and decision policy. The synthetic fixture runs offline.</p>
        {data.projects.isError ? (
          <ErrorBox message="API unavailable. Start the local API, then reload." />
        ) : (
          <>
            <label>Field project
              <select value={actualProject} disabled={data.projects.isLoading || !data.projects.data?.length}
                onChange={e => { setProjectId(e.target.value); setScenarioId(''); }}>
                <option value="">{data.projects.isLoading ? 'Loading…' : 'Choose a project'}</option>
                {data.projects.data?.map((p: Project) => <option value={p.id} key={p.id}>{p.name}</option>)}
              </select>
            </label>
            <label>Season scenario
              <select value={chosen} disabled={!actualProject || scenarios.isLoading}
                onChange={e => setScenarioId(e.target.value)}>
                <option value="">{scenarios.isLoading ? 'Loading…' : 'Choose a scenario'}</option>
                {scenarios.data?.map(s => <option value={s.id} key={s.id}>{s.name} · {s.budget_mm} mm</option>)}
              </select>
            </label>
            <fieldset className="controller-picker">
              <legend>Decision policy</legend>
              {CONTROLS.map(c => (
                <label className={`controller-card ${controller === c.id ? 'selected' : ''}`} key={c.id}>
                  <input type="radio" name="ctrl" value={c.id} checked={controller === c.id} onChange={() => setController(c.id)} />
                  <span style={{ borderLeft: `3px solid ${c.color}`, paddingLeft: 8 }}>
                    <b>{c.label}</b><small>{c.desc}</small>
                  </span>
                </label>
              ))}
            </fieldset>
            <label>Weather source
              <select value={datasetId} onChange={e => setDatasetId(e.target.value)}>
                {data.datasets.data?.map((d: Dataset) => (
                  <option value={d.id} key={d.id}>
                    {d.source === 'nasa_power' ? 'NASA POWER' : 'Synthetic fixture'} · {d.days} days
                  </option>
                ))}
              </select>
            </label>
            <label>Seed (0–2B)
              <input type="number" min="0" max="2147483647" value={seed} onChange={e => setSeed(Number(e.target.value))} />
            </label>
            <button className="button" disabled={!chosen || enqueue.isPending} onClick={() => enqueue.mutate()}>
              <Play size={15} />{enqueue.isPending ? 'Queueing…' : 'Run simulation'}
            </button>
            {!chosen && <p className="note">Create a field project and scenario first.</p>}
            {enqueue.isError && <ErrorBox message={String(enqueue.error)} />}
          </>
        )}
      </Panel>

      <Panel title="Job queue">
        {data.jobs.data?.filter((j: Job) => j.kind === 'simulation').length ? (
          <div className="list">
            {data.jobs.data?.filter((j: Job) => j.kind === 'simulation').slice(0, 8).map((job: Job) => (
              <div className="list-item" key={job.id}>
                <StatusBadge status={job.status} />
                <span>
                  <b>{job.controller}</b>
                  <small>{job.id.slice(0, 8)} · {job.progress}% · seed {job.seed}</small>
                </span>
                {(job.status === 'queued' || job.status === 'running') && <CancelButton id={job.id} />}
                {job.error && <small style={{ color: '#a4492d' }}>{job.error.slice(0, 60)}</small>}
              </div>
            ))}
          </div>
        ) : <Empty text="No simulation jobs. Select a scenario and run it." icon={<Droplets size={28} />} />}
      </Panel>

      {data.runs.data?.length ? (
        <Panel title="Saved runs — select to view daily trace" className="span-two">
          <div className="list" style={{ marginBottom: 16 }}>
            {data.runs.data.slice(0, 6).map((r: Run) => (
              <button
                className={`list-item ${runForChart === r.id ? 'chosen' : ''}`}
                key={r.id}
                onClick={() => setSelectedRun(r.id)}
              >
                <span className="run-icon"><Droplets size={14} /></span>
                <span>
                  <b>{r.controller} · {new Date(r.created_at).toLocaleString()}</b>
                  <small>{r.summary.days} days · {r.summary.seasonal_irrigation_mm.toFixed(0)} mm · {r.summary.dataset_source || 'synthetic'}</small>
                </span>
                <span style={{ textAlign: 'right' }}>
                  <strong>{r.summary.aquacrop ? `${r.summary.aquacrop.aquacrop_simulated_dry_yield_t_ha.toFixed(2)} t/ha` : '—'}</strong>
                  <small style={{ display: 'block', color: 'var(--muted)', fontSize: 10 }}>AquaCrop simulated</small>
                </span>
              </button>
            ))}
          </div>

          {chartData?.length ? (
            <>
              <h3 style={{ marginBottom: 8 }}>
                Daily water — {data.runs.data.find((r: Run) => r.id === runForChart)?.controller || ''} controller
              </h3>
              <div style={{ display: 'flex', gap: 16, marginBottom: 8, flexWrap: 'wrap' }}>
                <ChartLegendLabel color={CHART_COLORS.rain} label="Rainfall (mm)" />
                <ChartLegendLabel color={CHART_COLORS.irrigation} label="Irrigation applied (mm)" />
              </div>
              <ResponsiveContainer width="100%" height={170}>
                <BarChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }} barCategoryGap="2%">
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                  <XAxis dataKey="day" tick={{ fontSize: 9, fill: 'var(--muted)' }} />
                  <YAxis tick={{ fontSize: 10, fill: 'var(--muted)' }} unit=" mm" />
                  <Tooltip {...tooltipStyle} />
                  <Bar dataKey="rain" fill={CHART_COLORS.rain} name="Rain (mm)" stackId="a" />
                  <Bar dataKey="irrigation" fill={CHART_COLORS.irrigation} name="Irrigation (mm)" stackId="a" />
                </BarChart>
              </ResponsiveContainer>

              <div style={{ marginTop: 20 }}>
                <div style={{ display: 'flex', gap: 16, marginBottom: 8, flexWrap: 'wrap' }}>
                  <ChartLegendLabel color={CHART_COLORS.storage} label="Est. root-zone storage (mm)" />
                  <ChartLegendLabel color={CHART_COLORS.stress} label="Stress proxy (right axis)" />
                </div>
                <ResponsiveContainer width="100%" height={150}>
                  <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                    <XAxis dataKey="day" tick={{ fontSize: 9, fill: 'var(--muted)' }} />
                    <YAxis yAxisId="left" tick={{ fontSize: 10, fill: 'var(--muted)' }} unit=" mm" />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: 'var(--muted)' }} domain={[0, 1]} />
                    <Tooltip {...tooltipStyle} />
                    <Line yAxisId="left" type="monotone" dataKey="storage" stroke={CHART_COLORS.storage} strokeWidth={2} dot={false} name="Est. storage (mm)" />
                    <Line yAxisId="right" type="monotone" dataKey="stress" stroke={CHART_COLORS.stress} strokeWidth={1.5} dot={false} name="Stress proxy" strokeDasharray="4 2" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : daily.isLoading ? (
            <p style={{ color: 'var(--muted)', fontSize: 13 }}>Loading daily trace…</p>
          ) : null}
        </Panel>
      ) : null}
    </div>
  );
}
