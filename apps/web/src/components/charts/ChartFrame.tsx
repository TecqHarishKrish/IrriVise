import * as React from 'react';
import { Download, Table2 } from 'lucide-react';
import { downloadText, toCsv } from '@/lib/utils';
import { Button } from '../ui/button';
import { Card } from '../ui/card';
import { ProvenanceBadge, type Provenance } from '../common';

/**
 * Chart container with title, units, provenance, an accessible data-table alternative,
 * and SVG/CSV download of exactly the plotted rows.
 */
export function ChartFrame<T extends Record<string, unknown>>({ title, description, provenance, rows, columns, children, height = 280, name }: {
  title: string; description?: React.ReactNode; provenance?: Provenance[]; rows: T[]; columns: { key: keyof T & string; label: string }[];
  children: React.ReactNode; height?: number; name: string;
}) {
  const [table, setTable] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const id = React.useId();
  const saveSvg = () => {
    const svg = ref.current?.querySelector('svg.recharts-surface') ?? ref.current?.querySelector('svg');
    if (!svg) return;
    const clone = svg.cloneNode(true) as SVGElement;
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    const style = getComputedStyle(document.body);
    clone.setAttribute('style', `background:${style.backgroundColor};font-family:sans-serif`);
    downloadText(`${name}.svg`, `<?xml version="1.0"?>\n<!-- ${title} — IrriVise (simulated data) -->\n${clone.outerHTML}`, 'image/svg+xml');
  };
  return (
    <Card className="flex min-w-0 flex-col p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id={id} className="text-sm font-semibold">{title}</h3>
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
          {provenance && <div className="mt-1.5 flex flex-wrap gap-1">{provenance.map((p) => <ProvenanceBadge key={p} kind={p} />)}</div>}
        </div>
        <div className="no-print flex gap-1">
          <Button variant="ghost" size="sm" aria-pressed={table} onClick={() => setTable((t) => !t)}><Table2 aria-hidden />{table ? 'Chart' : 'Table'}</Button>
          <Button variant="ghost" size="sm" onClick={saveSvg} disabled={table} aria-label={`Download ${title} as SVG`}><Download aria-hidden />SVG</Button>
          <Button variant="ghost" size="sm" onClick={() => downloadText(`${name}.csv`, toCsv(rows.map((r) => Object.fromEntries(columns.map((c) => [c.label, r[c.key]])))), 'text/csv')} aria-label={`Download ${title} data as CSV`}>CSV</Button>
        </div>
      </div>
      {table ? (
        <div className="max-h-[360px] overflow-auto rounded-md border">
          <table className="w-full text-xs" aria-labelledby={id}>
            <thead className="sticky top-0 bg-muted"><tr>{columns.map((c) => <th key={c.key} scope="col" className="px-2 py-1.5 text-left font-medium">{c.label}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t">{columns.map((c) => <td key={c.key} className="tabular px-2 py-1">{r[c.key] === null || r[c.key] === undefined ? '—' : typeof r[c.key] === 'number' ? Number(r[c.key]).toFixed(3).replace(/\.?0+$/, '') : String(r[c.key])}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={ref} role="img" aria-labelledby={id} className="w-full overflow-x-auto" style={{ height }}>
          <div className="h-full min-w-[520px]">{children}</div>
        </div>
      )}
    </Card>
  );
}

export const CHART = {
  grid: 'hsl(var(--border))',
  axis: 'hsl(var(--muted-foreground))',
  c1: 'hsl(var(--chart-1))',
  c2: 'hsl(var(--chart-2))',
  c3: 'hsl(var(--chart-3))',
  c4: 'hsl(var(--chart-4))',
  c5: 'hsl(var(--chart-5))',
  band: 'hsl(var(--chart-1) / 0.18)',
  danger: 'hsl(var(--destructive))',
};

export const tooltipStyle = {
  contentStyle: { background: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))', borderRadius: 8, fontSize: 12, color: 'hsl(var(--popover-foreground))' },
  labelStyle: { color: 'hsl(var(--muted-foreground))' },
};
