import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { CloudDownload, Download, FileUp, Satellite } from 'lucide-react';
import { api, errorMessage } from '@/api/client';
import { mutations, useDatasetPreview, useDatasets, useInvalidate } from '@/api/hooks';
import type { Dataset } from '@/api/types';
import { useWorkspace } from '@/app/workspace';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input, Select } from '@/components/ui/input';
import { ErrorPanel, Field, LoadingBlock, Notice, PageHeader, ProvenanceBadge, Term, datasetProvenance } from '@/components/common';
import { ChartFrame, CHART, tooltipStyle } from '@/components/charts/ChartFrame';
import { JobCard } from '@/components/JobCard';
import { cn, fmt } from '@/lib/utils';

const nasaSchema = z.object({
  name: z.string().trim().min(2).max(120),
  latitude: z.coerce.number().min(-90).max(90),
  longitude: z.coerce.number().min(-180).max(180),
  start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'YYYY-MM-DD'),
  end: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'YYYY-MM-DD'),
  time_standard: z.enum(['LST', 'UTC']),
}).refine((v) => v.end >= v.start, { message: 'End must be on or after start', path: ['end'] })
  .refine((v) => new Date(v.end) < new Date(new Date().toDateString()), { message: 'End date must be in the past', path: ['end'] });
type NasaForm = z.infer<typeof nasaSchema>;

function ImportCard() {
  const refresh = useInvalidate();
  const [file, setFile] = React.useState<File | null>(null);
  const [name, setName] = React.useState('');
  const [result, setResult] = React.useState<{ ok: boolean; text: string; details?: string[] } | null>(null);
  const [busy, setBusy] = React.useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return setResult({ ok: false, text: 'Choose a .csv file first' });
    if (file.size > 5_000_000) return setResult({ ok: false, text: 'File exceeds the 5 MB limit' });
    setBusy(true);
    const body = new FormData();
    body.append('file', file);
    body.append('name', name.trim() || file.name.replace(/\.csv$/i, ''));
    try {
      const d = await api<Dataset>('/datasets/import', { method: 'POST', body });
      setResult({ ok: true, text: `Imported ${d.rows} rows (${d.start} → ${d.end}).`, details: d.validation.warnings });
      refresh('datasets');
    } catch (err) {
      const details = (err as { details?: { errors?: string[] } }).details?.errors;
      setResult({ ok: false, text: errorMessage(err), details });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><FileUp className="size-4" aria-hidden />Import weather CSV</CardTitle>
        <CardDescription>Columns: <code>date,rain_mm,eto_mm,tmin_c,tmax_c</code> (YYYY-MM-DD, mm/day, °C). Max 5 MB. Duplicates, malformed dates, negative rain or Tmin &gt; Tmax are rejected; NaN rows are quarantined, never imputed.</CardDescription></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field label="CSV file" htmlFor="csv-file"><Input id="csv-file" type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
          <Field label="Dataset name" htmlFor="csv-name"><Input id="csv-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Station records 2010–2020" /></Field>
          <Button type="submit" disabled={busy}>{busy ? 'Validating…' : 'Validate & import'}</Button>
          {result && (
            <div role="status" className={cn('rounded-md border p-3 text-sm', result.ok ? 'border-success/30 bg-success-soft' : 'border-destructive/30 bg-destructive-soft')}>
              <p className={result.ok ? 'text-success' : 'text-destructive'}>{result.text}</p>
              {result.details && result.details.length > 0 && <ul className="mt-1 list-disc pl-5 text-xs">{result.details.map((d) => <li key={d}>{d}</li>)}</ul>}
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

function NasaCard() {
  const ws = useWorkspace();
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const year = new Date().getFullYear();
  const form = useForm<NasaForm>({ resolver: zodResolver(nasaSchema), defaultValues: {
    name: 'NASA POWER daily — Tiruchirappalli', latitude: ws.scenario?.latitude ?? 10.79, longitude: ws.scenario?.longitude ?? 78.7,
    start: `${year - 16}-01-01`, end: `${year - 1}-12-31`, time_standard: 'LST' } });
  const submit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      const job = await mutations.nasa(v);
      setJobId(job.id);
    } catch (e) {
      setError(errorMessage(e));
    }
  });
  const err = form.formState.errors;
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Satellite className="size-4" aria-hidden />NASA POWER daily ingestion</CardTitle>
        <CardDescription>Fetches T2M_MAX, T2M_MIN, PRECTOTCORR, ALLSKY_SFC_SW_DWN, WS2M, RH2M (AG community) and computes FAO-56 Penman–Monteith ET₀. Bounded retries, timeout, cache. Runs in the worker.</CardDescription></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2" noValidate>
          <div className="sm:col-span-2"><Field label="Name" htmlFor="n-name" error={err.name?.message}><Input id="n-name" {...form.register('name')} /></Field></div>
          <Field label="Latitude (°)" htmlFor="n-lat" error={err.latitude?.message}><Input id="n-lat" type="number" step="0.01" {...form.register('latitude')} /></Field>
          <Field label="Longitude (°)" htmlFor="n-lon" error={err.longitude?.message}><Input id="n-lon" type="number" step="0.01" {...form.register('longitude')} /></Field>
          <Field label="Start" htmlFor="n-start" error={err.start?.message}><Input id="n-start" type="date" {...form.register('start')} /></Field>
          <Field label="End" htmlFor="n-end" error={err.end?.message}><Input id="n-end" type="date" {...form.register('end')} /></Field>
          <Field label="Time standard" htmlFor="n-ts" hint="POWER daily aggregation basis — not civil time."><Select id="n-ts" {...form.register('time_standard')}><option value="LST">LST (local solar time)</option><option value="UTC">UTC</option></Select></Field>
          <div className="flex items-end"><Button type="submit" className="w-full" disabled={form.formState.isSubmitting}><CloudDownload aria-hidden />Queue download</Button></div>
        </form>
        {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
        {jobId && <div className="mt-3"><JobCard jobId={jobId} title="NASA POWER fetch" /></div>}
        <p className="mt-3 text-xs text-muted-foreground">If the network is offline or NASA POWER is unreachable the job fails with a clear message; the synthetic sample dataset remains available.</p>
      </CardContent>
    </Card>
  );
}

function Preview({ dataset }: { dataset: Dataset }) {
  const ws = useWorkspace();
  const planting = ws.scenario?.planting_mmdd ?? '06-15';
  const length = ws.scenario?.season_length_days ?? 140;
  const preview = useDatasetPreview(dataset.id, planting, length);
  if (preview.isLoading) return <LoadingBlock rows={3} />;
  if (preview.isError) return <ErrorPanel error={preview.error} retry={() => preview.refetch()} />;
  const p = preview.data!;
  const v = dataset.validation;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="p-4"><p className="text-xs text-muted-foreground">Coverage</p><p className="tabular font-semibold">{dataset.start} → {dataset.end}</p><p className="text-xs text-muted-foreground">{dataset.rows.toLocaleString()} valid days</p></Card>
        <Card className="p-4"><p className="text-xs text-muted-foreground">Missingness</p><p className="tabular font-semibold">{Object.entries(v.missingness_pct ?? {}).map(([k, x]) => `${k} ${x}%`).join(' · ') || '—'}</p><p className="text-xs text-muted-foreground">{v.quarantined_count ?? 0} quarantined · {v.missing_dates ?? 0} absent dates</p></Card>
        <Card className="p-4"><p className="text-xs text-muted-foreground">Time standard</p><p className="font-semibold">{dataset.time_standard}</p><p className="text-xs text-muted-foreground">{dataset.latitude != null ? `${dataset.latitude}°, ${dataset.longitude}°` : 'no coordinates'}</p></Card>
        <Card className="p-4"><p className="text-xs text-muted-foreground">SHA-256</p><p className="break-all font-mono text-xs">{dataset.checksum_sha256}</p></Card>
      </div>
      {(v.warnings?.length ?? 0) > 0 && <Notice tone="warning">{v.warnings.join(' · ')}</Notice>}
      <ChartFrame name={`weather-${dataset.id.slice(0, 8)}`} title="Daily rainfall and reference ET" description={p.series_decimated ? `Evenly sampled ${p.series.length} of ${dataset.rows} days for display (values copied, not interpolated).` : 'All days shown.'}
        provenance={[datasetProvenance(dataset.source)]} rows={p.series as unknown as Record<string, unknown>[]}
        columns={[{ key: 'date', label: 'Date' }, { key: 'rain_mm', label: 'Rain (mm/day)' }, { key: 'eto_mm', label: 'ET0 (mm/day)' }, { key: 'tmin_c', label: 'Tmin (°C)' }, { key: 'tmax_c', label: 'Tmax (°C)' }]}>
        <ResponsiveContainer>
          <ComposedChart data={p.series} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" stroke={CHART.axis} fontSize={11} minTickGap={40} />
            <YAxis stroke={CHART.axis} fontSize={11} width={44} label={{ value: 'mm/day', angle: -90, position: 'insideLeft', fill: CHART.axis, fontSize: 11 }} />
            <Tooltip {...tooltipStyle} />
            <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="rain_mm" name="Rain (mm/day)" fill={CHART.c2} isAnimationActive={false} />
            <Line dataKey="eto_mm" name="ET0 (mm/day)" stroke={CHART.c3} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Card>
        <CardHeader><CardTitle><Term id="split">Growing seasons and chronological split</Term></CardTitle>
          <CardDescription>Planting {planting}, {length} days (from the active scenario). Rule: {p.split.rule}.</CardDescription></CardHeader>
        <CardContent>
          <div className="mb-3 flex flex-wrap gap-2 text-xs">
            <Badge variant="default">train {p.split.train.length}</Badge><Badge variant="info">validation {p.split.validation.length}</Badge><Badge variant="warning">test (held out) {p.split.test.length}</Badge>
          </div>
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6" aria-label="Seasons">
            {p.seasons.map((s) => (
              <li key={s.season_id} className={cn('rounded-md border p-2 text-xs', s.split === 'test' ? 'border-warning/40 bg-warning-soft' : s.split === 'validation' ? 'bg-accent' : 'bg-secondary')}>
                <span className="block font-semibold">{s.season_id} · {s.split}</span><span className="tabular">{fmt(s.rain_mm, 0)} mm rain</span>
              </li>
            ))}
          </ul>
          {p.skipped_seasons.length > 0 && <p className="mt-2 text-xs text-muted-foreground">Skipped: {p.skipped_seasons.join('; ')}</p>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>First rows</CardTitle><CardDescription>Validated canonical schema</CardDescription></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm"><thead className="text-left text-xs text-muted-foreground"><tr><th className="p-1.5">Date</th><th className="p-1.5">Rain (mm/day)</th><th className="p-1.5">ET₀ (mm/day)</th><th className="p-1.5">Tmin (°C)</th><th className="p-1.5">Tmax (°C)</th></tr></thead>
            <tbody>{p.head.map((r) => <tr key={r.date} className="tabular border-t"><td className="p-1.5">{r.date}</td><td className="p-1.5">{r.rain_mm}</td><td className="p-1.5">{r.eto_mm}</td><td className="p-1.5">{r.tmin_c}</td><td className="p-1.5">{r.tmax_c}</td></tr>)}</tbody></table>
        </CardContent>
      </Card>
      <Card><CardHeader><CardTitle>Provenance & license</CardTitle></CardHeader><CardContent><pre className="overflow-x-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">{JSON.stringify(dataset.provenance, null, 2)}</pre><p className="mt-2 text-xs text-muted-foreground">{dataset.license}</p></CardContent></Card>
    </div>
  );
}

export default function DataStudio() {
  const datasets = useDatasets();
  const ws = useWorkspace();
  const [selected, setSelected] = React.useState<string | null>(null);
  const id = selected ?? ws.scenario?.dataset_id ?? datasets.data?.[0]?.id ?? null;
  const dataset = datasets.data?.find((d) => d.id === id);
  return (
    <>
      <PageHeader title="Weather & Data Studio" description="Weather datasets with validation reports, provenance, checksums and whole-season chronological splits." />
      {datasets.isError && <ErrorPanel error={datasets.error} retry={() => datasets.refetch()} />}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card>
            <CardHeader><CardTitle>Datasets</CardTitle></CardHeader>
            <CardContent>
              {datasets.isLoading ? <LoadingBlock rows={2} /> : (
                <ul className="flex flex-col gap-2">
                  {datasets.data?.map((d) => (
                    <li key={d.id} className={cn('flex flex-wrap items-center gap-2 rounded-md border p-3', d.id === id && 'border-primary bg-secondary')}>
                      <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setSelected(d.id)} aria-pressed={d.id === id}>
                        <span className="block font-medium">{d.name}</span>
                        <span className="text-xs text-muted-foreground">{d.start} → {d.end} · {d.rows.toLocaleString()} days{d.id === ws.scenario?.dataset_id ? ' · used by active scenario' : ''}</span>
                      </button>
                      <ProvenanceBadge kind={datasetProvenance(d.source)} />
                      <Button variant="ghost" size="sm" asChild><a href={`/api/v1/datasets/${d.id}/download`} download><Download aria-hidden />CSV</a></Button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
          {dataset && <Preview dataset={dataset} />}
        </div>
        <div className="flex flex-col gap-4"><ImportCard /><NasaCard /></div>
      </div>
    </>
  );
}
