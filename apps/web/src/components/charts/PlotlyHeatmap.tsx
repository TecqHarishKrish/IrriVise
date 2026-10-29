import * as React from 'react';

type PlotlyLib = { newPlot: (el: HTMLElement, data: unknown[], layout: unknown, config: unknown) => Promise<unknown>; purge: (el: HTMLElement) => void };

/**
 * Advanced scientific inspection with Plotly.js (lazy-loaded so the main bundle stays small).
 * Renders a heatmap of Q̂(state, action) for the plausible ensemble.
 */
export function QHeatmap({ z, x, y, title }: { z: number[][]; x: string[]; y: string[]; title: string }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    const el = ref.current;
    import('plotly.js-cartesian-dist-min')
      .then((mod) => {
        if (cancelled || !el) return;
        const Plotly = ((mod as unknown as { default?: PlotlyLib }).default ?? mod) as PlotlyLib;
        const dark = document.documentElement.classList.contains('dark');
        const fg = dark ? '#dce8e2' : '#344054';
        Plotly.newPlot(el, [{ type: 'heatmap', z, x, y, colorscale: 'Viridis', colorbar: { title: { text: 'Q̂ (reward units)', side: 'right' }, tickfont: { color: fg } },
          hovertemplate: 'state %{y}<br>action %{x}<br>Q̂ %{z:.4f}<extra></extra>' }],
          { title: { text: title, font: { size: 13, color: fg } }, margin: { l: 90, r: 10, t: 36, b: 44 }, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
            xaxis: { title: { text: 'Candidate irrigation (mm)' }, color: fg }, yaxis: { title: { text: 'Plausible state (storage mm)' }, color: fg, automargin: true }, font: { color: fg } },
          { displaylogo: false, responsive: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] });
      })
      .catch((e) => setError(String(e)));
    return () => {
      cancelled = true;
      if (el) import('plotly.js-cartesian-dist-min').then((m) => ((m as unknown as { default?: PlotlyLib }).default ?? (m as unknown as PlotlyLib)).purge(el)).catch(() => undefined);
    };
  }, [z, x, y, title]);
  if (error) return <p className="text-sm text-destructive">Plot failed to load: {error}</p>;
  return <div ref={ref} className="h-[380px] w-full" role="img" aria-label={`${title}. Use the table view for exact values.`} />;
}
