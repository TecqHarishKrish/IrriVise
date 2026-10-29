import * as React from 'react';
import { useLocation } from 'react-router-dom';
import { Moon, RotateCcw, Sun } from 'lucide-react';
import { errorMessage } from '@/api/client';
import { mutations, useDefaults, useDiagnostics, useInvalidate } from '@/api/hooks';
import { useTheme } from '@/app/theme';
import { useWorkspace } from '@/app/workspace';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ErrorPanel, LoadingBlock, Notice, PageHeader } from '@/components/common';
import { GLOSSARY } from '@/lib/glossary';

const gb = (b?: number | null) => (b == null ? '—' : `${(b / 1e9).toFixed(1)} GB`);

const LIMITATIONS = [
  'All outcomes come from a simulated reference farm; nothing here is a field measurement or a field validation.',
  'The fast water-balance surrogate is a single-layer FAO-56 model; it is not calibrated against AquaCrop or field data, and AquaCrop’s default maize/soil parameters differ from it (structural model mismatch).',
  'Yield proxy = FAO-33 stage yield response × 9 t/ha; AquaCrop yields replay the applied schedule with default parameters. Neither is measured yield.',
  'CARAT regret and VOI are estimates under the twin’s own model with a 5-day forecast-driven lookahead and a heuristic rollout policy; they are not oracle quantities.',
  'Forecasts are training-season climatology + persistence; real forecast skill is not modelled.',
  'Quick PPO models are smoke tests. Research claims require the standard/research presets, multiple seeds and held-out evaluation.',
  'Single-user local mode: no authentication; keep the API bound to localhost.',
];

export default function SettingsPage() {
  const diag = useDiagnostics();
  const defaults = useDefaults();
  const { dark, toggle } = useTheme();
  const ws = useWorkspace();
  const refresh = useInvalidate();
  const location = useLocation();
  const [msg, setMsg] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (location.hash === '#help') document.getElementById('help')?.scrollIntoView();
  }, [location.hash]);

  const reset = async () => {
    setMsg(null);
    try {
      const r = (await mutations.resetSample()) as { project: { id: string }; scenario: { id: string } };
      ws.select(r.project.id, r.scenario.id);
      refresh('projects', 'scenarios', 'datasets');
      setMsg('Sample dataset re-verified and sample field restored. Your own data and results were not touched.');
    } catch (e) {
      setMsg(errorMessage(e));
    }
  };
  const restartOnboarding = () => {
    try {
      localStorage.removeItem('irrivise.onboarding.dismissed');
    } catch {
      /* ignore */
    }
    setMsg('Onboarding will reappear when no project exists.');
  };
  const d = diag.data;

  return (
    <>
      <PageHeader title="Settings & Help" description="Diagnostics, environment, units, methodology, glossary and limitations." />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Environment diagnostics</CardTitle><CardDescription>Live from the API.</CardDescription></CardHeader>
          <CardContent>
            {diag.isError ? <ErrorPanel error={diag.error} retry={() => diag.refetch()} /> : !d ? <LoadingBlock rows={3} /> : (
              <dl className="grid grid-cols-2 gap-y-2 text-sm">
                <dt className="text-muted-foreground">API · database · schema</dt><dd>{d.health.api} · {d.health.database} · rev {d.health.schema_revision}</dd>
                <dt className="text-muted-foreground">Worker</dt><dd><Badge variant={d.health.worker.status === 'online' ? 'success' : 'warning'}>{d.health.worker.status}</Badge></dd>
                <dt className="text-muted-foreground">CPU cores · memory</dt><dd className="tabular">{d.cpu_count} · {gb(d.memory.total_bytes)}</dd>
                <dt className="text-muted-foreground">Disk free · artifacts</dt><dd className="tabular">{gb(d.disk.free_bytes)} · {(d.disk.artifacts_bytes / 1e6).toFixed(1)} MB</dd>
                <dt className="text-muted-foreground">Data paths</dt><dd className="font-mono text-xs">{Object.values(d.paths).join(' · ')}</dd>
                <dt className="text-muted-foreground">Limits</dt><dd className="text-xs">{Object.entries(d.limits).map(([k, v]) => `${k}=${v}`).join(', ')}</dd>
                <dt className="text-muted-foreground">Mode</dt><dd className="text-xs">{d.health.mode}</dd>
                {Object.entries(d.packages).map(([k, v]) => <React.Fragment key={k}><dt className="text-muted-foreground">{k}</dt><dd className="font-mono text-xs">{v}</dd></React.Fragment>)}
              </dl>
            )}
          </CardContent>
        </Card>
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader><CardTitle>Preferences & data</CardTitle></CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Button variant="outline" onClick={toggle} className="w-fit">{dark ? <Sun aria-hidden /> : <Moon aria-hidden />}Switch to {dark ? 'light' : 'dark'} theme</Button>
              <Button variant="outline" onClick={reset} className="w-fit"><RotateCcw aria-hidden />Reset sample data</Button>
              <Button variant="ghost" onClick={restartOnboarding} className="w-fit">Show onboarding again</Button>
              {msg && <Notice tone="success">{msg}</Notice>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Units</CardTitle></CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-y-1 text-sm">{Object.entries(defaults.data?.units ?? {}).map(([k, v]) => <React.Fragment key={k}><dt className="text-muted-foreground">{k.replace(/_/g, ' ')}</dt><dd>{v}</dd></React.Fragment>)}</dl>
              <p className="mt-2 text-xs text-muted-foreground">1 mm of water over 1 ha = 10 m³. Storage (mm) = θ (m³/m³) × root depth (m) × 1000.</p>
            </CardContent>
          </Card>
        </div>
        <Card className="xl:col-span-2">
          <CardHeader><CardTitle>Methodology in brief</CardTitle><CardDescription>Full formulas in METHODOLOGY.md.</CardDescription></CardHeader>
          <CardContent className="grid gap-4 text-sm md:grid-cols-2">
            <ol className="list-decimal space-y-1.5 pl-5">
              <li><strong>Reference farm</strong> (hidden): FAO-56 root-zone water balance with a random draw of soil parameters; realized weather.</li>
              <li><strong>Digital twin</strong>: {String(defaults.data?.uncertainty.ensemble_size ?? '—')} plausible states from the same prior, propagated with observed (noisy) past weather.</li>
              <li><strong>Policy</strong>: PPO (or a baseline) proposes 0/5/10/15/20 mm from the twin, forecast and budgets only.</li>
              <li><strong>CARAT</strong>: Q̂ over states × actions ({String(defaults.data?.carat.horizon_days ?? 5)}-day lookahead) → estimated regret → VOI from {String(defaults.data?.carat.hypothetical_samples ?? 16)} hypothetical readings → observe iff net VOI &gt; threshold.</li>
              <li><strong>Correction</strong>: K = P/(P+R); mean' = mean + K(z − mean); P' = (1 − K)P.</li>
              <li><strong>Risk manager</strong>: hard daily/seasonal limits always; soft stress/waste adjustments with explicit reasons.</li>
              <li><strong>Evaluator</strong>: after the season, compares twin vs hidden truth and computes metrics.</li>
            </ol>
            <div>
              <p className="mb-1 font-medium">Policy observation features ({defaults.data?.feature_spec_version})</p>
              <ul className="grid gap-0.5 text-xs text-muted-foreground">{defaults.data?.policy_features.map((f) => <li key={f.name}><code>{f.name}</code> — {f.description}</li>)}</ul>
            </div>
          </CardContent>
        </Card>
        <Card id="help" className="scroll-mt-20 xl:col-span-2">
          <CardHeader><CardTitle>Glossary</CardTitle></CardHeader>
          <CardContent><dl className="grid gap-3 md:grid-cols-2">{Object.values(GLOSSARY).map((g) => <div key={g.term}><dt className="font-medium">{g.term}</dt><dd className="text-sm text-muted-foreground">{g.text}</dd></div>)}</dl></CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader><CardTitle>Limitations</CardTitle></CardHeader>
          <CardContent><ul className="list-disc space-y-1 pl-5 text-sm">{LIMITATIONS.map((l) => <li key={l}>{l}</li>)}</ul></CardContent>
        </Card>
      </div>
    </>
  );
}
