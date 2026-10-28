import * as React from 'react';
import { Download, ExternalLink, FileText } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { mutations, useExperiments, useExports, useInvalidate, useModels, useRuns } from '@/api/hooks';
import { useWorkspace } from '@/app/workspace';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select } from '@/components/ui/input';
import { EmptyState, Field, LoadingBlock, Notice, PageHeader } from '@/components/common';
import { relativeTime, shortId } from '@/lib/utils';

const FORMATS: Record<string, { value: string; label: string }[]> = {
  run: [{ value: 'zip', label: 'ZIP bundle (daily CSV, decisions JSON, evaluation truth, manifest, report)' }, { value: 'html', label: 'Printable HTML report' }, { value: 'csv', label: 'Daily trace CSV' }, { value: 'json', label: 'Run summary + manifest JSON' }],
  experiment: [{ value: 'zip', label: 'ZIP bundle (results CSV, summary, manifest, report)' }, { value: 'html', label: 'Printable HTML report' }, { value: 'csv', label: 'Per-run results CSV' }, { value: 'json', label: 'Summary JSON' }],
  model: [{ value: 'zip', label: 'Manifest + learning-curve report (no binaries)' }, { value: 'html', label: 'Printable HTML report' }, { value: 'json', label: 'Model metadata JSON' }],
};

export default function Reports() {
  const ws = useWorkspace();
  const runs = useRuns(ws.scenarioId);
  const experiments = useExperiments(ws.scenarioId);
  const models = useModels(ws.scenarioId);
  const exports = useExports();
  const refresh = useInvalidate();
  const [type, setType] = React.useState<'run' | 'experiment' | 'model'>('run');
  const [source, setSource] = React.useState('');
  const [format, setFormat] = React.useState('zip');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const options = type === 'run' ? (runs.data ?? []).map((r) => ({ id: r.id, label: `${r.method_code} · ${r.method_label} · season ${r.season_id} · seed ${r.seed}` }))
    : type === 'experiment' ? (experiments.data ?? []).filter((e) => e.status === 'succeeded').map((e) => ({ id: e.id, label: `${e.name} · ${e.n_runs} runs` }))
      : (models.data ?? []).map((m) => ({ id: m.id, label: `${m.preset} · seed ${m.seed} · ${m.actual_timesteps.toLocaleString()} steps` }));
  const selected = source && options.some((o) => o.id === source) ? source : options[0]?.id ?? '';

  const create = async (open: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const record = await mutations.createExport({ source_type: type, source_id: selected, format });
      refresh('exports');
      if (open) window.open(record.download_url, '_blank', 'noopener');
      else window.location.assign(record.download_url);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Report & Export Center" description="Exports are generated from saved artifacts after re-verifying their SHA-256 hashes, so downloaded numbers reconcile with what the UI shows." />
      <div className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <Card>
          <CardHeader><CardTitle>Create an export</CardTitle><CardDescription>Manifests include seeds, configuration hash, dataset checksum, model checksum, code revision and package versions.</CardDescription></CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Field label="Source" htmlFor="e-type">
              <Select id="e-type" value={type} onChange={(e) => { setType(e.target.value as typeof type); setFormat('zip'); setSource(''); }}>
                <option value="run">Simulation run</option><option value="experiment">Experiment</option><option value="model">PPO model</option>
              </Select>
            </Field>
            <Field label="Item" htmlFor="e-source" error={!options.length ? `No ${type}s available for the active scenario` : undefined}>
              <Select id="e-source" value={selected} onChange={(e) => setSource(e.target.value)} disabled={!options.length}>{options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}</Select>
            </Field>
            <Field label="Format" htmlFor="e-format">
              <Select id="e-format" value={format} onChange={(e) => setFormat(e.target.value)}>{FORMATS[type].map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</Select>
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button disabled={!selected || busy} onClick={() => create(false)}><Download aria-hidden />Generate & download</Button>
              {format === 'html' && <Button variant="outline" disabled={!selected || busy} onClick={() => create(true)}><ExternalLink aria-hidden />Open printable report</Button>}
            </div>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <Notice>Charts on every page also offer SVG and CSV downloads of exactly the plotted data. Use the browser’s Print → “Save as PDF” on an HTML report for a PDF.</Notice>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Export history</CardTitle><CardDescription>Immutable files; re-download is refused if a file was modified.</CardDescription></CardHeader>
          <CardContent>
            {exports.isLoading ? <LoadingBlock rows={2} /> : !exports.data?.length ? <EmptyState icon={FileText} title="No exports yet" description="Generate one from a run, experiment or model." /> : (
              <ul className="divide-y">
                {exports.data.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                    <span className="min-w-0">
                      <Badge variant="outline" className="mr-2 uppercase">{e.format}</Badge>{e.source_type} {shortId(e.source_id)}
                      <span className="block font-mono text-[11px] text-muted-foreground">sha256 {e.sha256.slice(0, 16)}… · {(e.bytes / 1024).toFixed(1)} KiB · {relativeTime(e.created_at)}</span>
                    </span>
                    <Button variant="ghost" size="sm" asChild><a href={e.download_url} target={e.format === 'html' ? '_blank' : undefined} rel="noopener"><Download aria-hidden />Download</a></Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
