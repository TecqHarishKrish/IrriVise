import * as React from 'react';
import { AlertTriangle, Database, FlaskConical, HelpCircle, Info, RefreshCw, ShieldAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { GLOSSARY } from '@/lib/glossary';
import { errorMessage } from '@/api/client';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Skeleton } from './ui/misc';
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip';

export function PageHeader({ title, description, actions, eyebrow }: { title: string; description?: React.ReactNode; actions?: React.ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-primary">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold text-foreground sm:text-[1.7rem]">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

/** Contextual explanation of a scientific term (keyboard-focusable). */
export function Term({ id, children }: { id: keyof typeof GLOSSARY; children?: React.ReactNode }) {
  const entry = GLOSSARY[id];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" className="inline-flex items-center gap-1 rounded underline decoration-dotted underline-offset-4 hover:text-primary" aria-label={`What is ${entry.term}?`}>
          {children ?? entry.term}
          <HelpCircle className="size-3.5 text-muted-foreground" aria-hidden />
        </button>
      </TooltipTrigger>
      <TooltipContent><strong className="block">{entry.term}</strong>{entry.text}</TooltipContent>
    </Tooltip>
  );
}

export type Provenance = 'simulated' | 'estimated' | 'proxy' | 'aquacrop' | 'synthetic' | 'nasa' | 'uploaded' | 'truth' | 'model' | 'config';
const PROV: Record<Provenance, { label: string; variant: 'warning' | 'info' | 'default' | 'success' | 'destructive' | 'outline' }> = {
  simulated: { label: 'Simulated', variant: 'info' },
  estimated: { label: 'Twin estimate', variant: 'default' },
  proxy: { label: 'Yield proxy', variant: 'warning' },
  aquacrop: { label: 'AquaCrop-simulated', variant: 'success' },
  synthetic: { label: 'Synthetic demo data', variant: 'warning' },
  nasa: { label: 'NASA POWER historical', variant: 'info' },
  uploaded: { label: 'Uploaded data', variant: 'outline' },
  truth: { label: 'Simulated reference · evaluation only', variant: 'destructive' },
  model: { label: 'Model estimate', variant: 'default' },
  config: { label: 'Configuration', variant: 'outline' },
};

export function ProvenanceBadge({ kind, className }: { kind: Provenance; className?: string }) {
  const p = PROV[kind];
  return (
    <Badge variant={p.variant} className={className}>
      {kind === 'truth' ? <ShieldAlert aria-hidden /> : <Info aria-hidden />}
      {p.label}
    </Badge>
  );
}

export function datasetProvenance(source?: string): Provenance {
  return source === 'sample' ? 'synthetic' : source === 'nasa_power' ? 'nasa' : 'uploaded';
}

export function Kpi({ label, value, unit, provenance, hint, icon: Icon }: { label: React.ReactNode; value: string; unit?: string; provenance?: Provenance; hint?: React.ReactNode; icon?: React.ElementType }) {
  return (
    <Card className="flex min-w-0 flex-col gap-2 p-4">
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        {Icon && <Icon className="size-4 text-primary" aria-hidden />}
      </div>
      <div className="tabular text-2xl font-semibold leading-none text-foreground">
        {value}
        {unit && value !== '—' && <span className="ml-1 text-sm font-medium text-muted-foreground">{unit}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {provenance && <ProvenanceBadge kind={provenance} />}
        {hint}
      </div>
    </Card>
  );
}

export function EmptyState({ title, description, action, icon: Icon = Database }: { title: string; description?: React.ReactNode; action?: React.ReactNode; icon?: React.ElementType }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-10 text-center">
      <Icon className="mb-3 size-8 text-primary/70" aria-hidden />
      <h3 className="text-base font-semibold">{title}</h3>
      {description && <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function ErrorPanel({ error, retry, title = 'Something went wrong' }: { error: unknown; retry?: () => void; title?: string }) {
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-lg border border-destructive/30 bg-destructive-soft p-4 text-sm sm:flex-row sm:items-center sm:justify-between">
      <div className="flex gap-3">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
        <div>
          <p className="font-semibold text-destructive">{title}</p>
          <p className="text-foreground/90">{errorMessage(error)}</p>
        </div>
      </div>
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          <RefreshCw aria-hidden /> Retry
        </Button>
      )}
    </div>
  );
}

export function Notice({ tone = 'info', children, className }: { tone?: 'info' | 'warning' | 'success'; children: React.ReactNode; className?: string }) {
  const styles = { info: 'border-accent-foreground/15 bg-accent text-accent-foreground', warning: 'border-warning/30 bg-warning-soft text-foreground', success: 'border-success/30 bg-success-soft text-foreground' };
  const Icon = tone === 'warning' ? AlertTriangle : Info;
  return (
    <div className={cn('flex gap-3 rounded-lg border p-3 text-sm', styles[tone], className)}>
      <Icon className={cn('mt-0.5 size-4 shrink-0', tone === 'warning' && 'text-warning')} aria-hidden />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function LoadingBlock({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('flex flex-col gap-3', className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-16 w-full" />)}
    </div>
  );
}

export function NeedScenario() {
  return (
    <EmptyState
      icon={FlaskConical}
      title="Choose a field scenario first"
      description="Select an active project and scenario in the top bar, or explore the synthetic sample field."
      action={<Button asChild><Link to="/projects">Go to Projects & Fields</Link></Button>}
    />
  );
}

export function Field({ label, htmlFor, error, hint, children }: { label: React.ReactNode; htmlFor: string; error?: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">{label}</label>
      {children}
      {error ? <p id={`${htmlFor}-error`} className="text-xs text-destructive" role="alert">{error}</p> : hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const variant = status === 'succeeded' ? 'success' : status === 'failed' || status === 'interrupted' ? 'destructive' : status === 'cancelled' ? 'outline' : status === 'running' ? 'info' : 'warning';
  return <Badge variant={variant} className="capitalize"><span aria-hidden className={cn('size-1.5 rounded-full bg-current', status === 'running' && 'animate-pulse-soft')} />{status}</Badge>;
}
