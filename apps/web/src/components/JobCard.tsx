import { Ban, Radio } from 'lucide-react';
import { useJob, useApiMutation, mutations } from '@/api/hooks';
import { useJobEvents } from '@/api/progress';
import { errorMessage } from '@/api/client';
import { fmt, relativeTime, shortId } from '@/lib/utils';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Progress } from './ui/misc';
import { ErrorPanel, StatusBadge } from './common';

/** Durable job status with live SSE progress (polling fallback), log excerpt and cancel. */
export function JobCard({ jobId, title, onDone }: { jobId: string; title?: string; onDone?: () => void }) {
  const job = useJob(jobId);
  const { events, transport } = useJobEvents(jobId);
  const cancel = useApiMutation(mutations.cancelJob, ['jobs', 'job']);
  if (job.isError) return <ErrorPanel error={job.error} retry={() => job.refetch()} />;
  const j = job.data;
  if (!j) return <Card className="p-4 text-sm text-muted-foreground">Loading job {shortId(jobId)}…</Card>;
  const active = j.status === 'queued' || j.status === 'running';
  const log = events.length ? events : j.log_excerpt ?? [];
  return (
    <Card className="flex flex-col gap-3 p-4" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold">{title ?? `${j.kind} job`} <span className="font-mono text-xs text-muted-foreground">#{shortId(j.id)}</span></p>
          <p className="text-xs text-muted-foreground">Queued {relativeTime(j.created_at)} · {j.phase}</p>
        </div>
        <div className="flex items-center gap-2">
          {active && <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" title="Live update channel"><Radio className="size-3" aria-hidden />{transport === 'sse' ? 'live (SSE)' : 'polling'}</span>}
          <StatusBadge status={j.status} />
          {active && (
            <Button variant="outline" size="sm" disabled={cancel.isPending || j.cancel_requested} onClick={() => cancel.mutate(j.id)}>
              <Ban aria-hidden /> {j.cancel_requested ? 'Cancelling…' : 'Cancel'}
            </Button>
          )}
          {!active && onDone && j.status === 'succeeded' && <Button size="sm" onClick={onDone}>View result</Button>}
        </div>
      </div>
      {j.total_steps > 0 && (
        <div className="flex items-center gap-3">
          <Progress value={j.progress} label={`${title ?? 'Job'} progress`} />
          <span className="tabular w-40 shrink-0 text-right text-xs text-muted-foreground">{j.current_step.toLocaleString()} / {j.total_steps.toLocaleString()} ({fmt(j.progress, 0)}%)</span>
        </div>
      )}
      {cancel.isError && <p className="text-xs text-destructive">{errorMessage(cancel.error)}</p>}
      {j.error && <p role="alert" className="rounded-md bg-destructive-soft p-2 font-mono text-xs text-destructive">{j.error}</p>}
      {log.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground">Event log ({log.length})</summary>
          <ol className="mt-2 max-h-48 overflow-y-auto rounded-md bg-muted p-2 font-mono">
            {log.slice(-60).map((e) => (
              <li key={e.sequence}>
                #{e.sequence} {new Date(e.timestamp).toLocaleTimeString()} [{e.status}] {e.phase}{e.message ? ` — ${e.message}` : ''}
                {e.metric_name ? ` · ${e.metric_name}=${fmt(e.metric_value, 3)}` : ''}
              </li>
            ))}
          </ol>
        </details>
      )}
    </Card>
  );
}
