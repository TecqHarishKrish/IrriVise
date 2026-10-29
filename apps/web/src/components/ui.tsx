import type React from 'react';
import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';

// ─── Panel ────────────────────────────────────────────────────────────────────
export function Panel({
  title, children, action, className,
}: {
  title: string; children: React.ReactNode;
  action?: React.ReactNode; className?: string;
}) {
  return (
    <section className={`panel ${className || ''}`}>
      <div className="panel-heading">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

// ─── ErrorBox ─────────────────────────────────────────────────────────────────
export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="error" role="alert">
      <AlertCircle size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
      {message}
    </div>
  );
}

// ─── Empty ────────────────────────────────────────────────────────────────────
export function Empty({ text, icon }: { text: string; icon?: React.ReactNode }) {
  return (
    <div className="empty">
      {icon && <div style={{ marginBottom: 10, opacity: 0.5 }}>{icon}</div>}
      <p style={{ margin: 0 }}>{text}</p>
    </div>
  );
}

// ─── Stat ─────────────────────────────────────────────────────────────────────
export function Stat({
  label, value, sub, accent,
}: { label: string; value: string; sub: string; accent?: boolean }) {
  return (
    <div className={`stat${accent ? ' stat-accent' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

// ─── StatusBadge ─────────────────────────────────────────────────────────────
export function StatusBadge({ status }: { status: string }) {
  const icon =
    status === 'running' ? <Loader2 size={10} className="spin" /> :
    status === 'succeeded' ? <CheckCircle2 size={10} /> :
    status === 'failed' ? <AlertCircle size={10} /> : null;
  return (
    <span className={`status ${status}`}>
      {icon && <span style={{ marginRight: 4 }}>{icon}</span>}
      {status}
    </span>
  );
}

// ─── ChartLegendLabel ─────────────────────────────────────────────────────────
export function ChartLegendLabel({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--muted)' }}>
      <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: 'inline-block' }} />
      {label}
    </span>
  );
}

// ─── ProgressBar ─────────────────────────────────────────────────────────────
export function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="progress-bar">
      <div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}

// ─── RunList ─────────────────────────────────────────────────────────────────
import { Droplets } from 'lucide-react';
import type { Run } from '../types';

export function RunList({ runs }: { runs: Run[] }) {
  if (!runs.length) return (
    <Empty text="No completed runs. Start a simulation to populate this view." icon={<Droplets size={28} />} />
  );
  return (
    <div className="list">
      {runs.slice(0, 8).map(r => (
        <div className="list-item" key={r.id}>
          <span className="run-icon"><Droplets size={16} /></span>
          <span>
            <b>{r.controller} controller</b>
            <small>
              {new Date(r.created_at).toLocaleString()} · {r.summary.days} days · seed {r.summary.seed ?? 42}
            </small>
          </span>
          <div style={{ textAlign: 'right' }}>
            <strong>{r.summary.seasonal_irrigation_mm.toFixed(0)} mm</strong>
            <small style={{ display: 'block', fontSize: 10, color: 'var(--muted)' }}>
              {r.summary.aquacrop
                ? `${r.summary.aquacrop.aquacrop_simulated_dry_yield_t_ha.toFixed(2)} t/ha`
                : `proxy ${r.summary.yield_proxy_t_ha.toFixed(2)} t/ha`}
            </small>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── CancelButton ─────────────────────────────────────────────────────────────
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';

export function CancelButton({ id }: { id: string }) {
  const qc = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api(`/api/v1/jobs/${id}/cancel`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs'] }),
  });
  return (
    <button className="ghost danger" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
      Cancel
    </button>
  );
}
