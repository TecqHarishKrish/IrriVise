import { Area, Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts';
import type { DailyRow, TruthRow } from '@/api/types';
import { ChartFrame, CHART, tooltipStyle } from './ChartFrame';

const axisProps = { stroke: CHART.axis, fontSize: 11, tickLine: false };

/** Twin belief: mean with 10–90 % ensemble band, field-capacity reference via RAW/TAW, readings marked. */
export function SoilWaterChart({ rows, truth, name = 'soil-water' }: { rows: DailyRow[]; truth?: TruthRow[] | null; name?: string }) {
  const data = rows.map((r, i) => ({
    day: r.day,
    band: [r.belief_q10_mm, r.belief_q90_mm] as [number, number],
    mean: r.belief_mean_mm,
    corrected: r.corrected_mean_mm,
    // storage at stress onset ≈ S_fc − RAW, with S_fc ≈ mean + depletion
    stress_threshold: r.belief_mean_mm + r.est_depletion_fraction * r.taw_mm - r.raw_mm,
    truth: truth?.[i]?.true_storage_mm ?? null,
    q10: r.belief_q10_mm,
    q90: r.belief_q90_mm,
  }));
  return (
    <ChartFrame
      name={name}
      title="Root-zone soil water — twin belief"
      description="Mean estimate (mm) with 10–90 % plausible-state band; dots mark corrected estimates after a soil reading. Dashed: stress onset (depletion = RAW)."
      provenance={truth ? ['estimated', 'truth'] : ['estimated']}
      rows={data.map(({ band: _b, ...d }) => d)}
      columns={[{ key: 'day', label: 'Day' }, { key: 'mean', label: 'Twin mean (mm)' }, { key: 'q10', label: 'q10 (mm)' }, { key: 'q90', label: 'q90 (mm)' },
        { key: 'corrected', label: 'Corrected mean (mm)' }, ...(truth ? [{ key: 'truth' as const, label: 'Simulated reference (mm, evaluation only)' }] : [])]}
      height={300}
    >
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
          <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="day" {...axisProps} label={{ value: 'Day of season', position: 'insideBottom', offset: -10, fill: CHART.axis, fontSize: 11 }} />
          <YAxis {...axisProps} width={52} label={{ value: 'Storage (mm)', angle: -90, position: 'insideLeft', fill: CHART.axis, fontSize: 11 }} domain={['auto', 'auto']} />
          <Tooltip {...tooltipStyle} formatter={(v: number | number[]) => (Array.isArray(v) ? `${v[0].toFixed(1)}–${v[1].toFixed(1)} mm` : `${Number(v).toFixed(1)} mm`)} />
          <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
          <Area dataKey="band" name="Plausible band (10–90 %)" stroke="none" fill={CHART.band} isAnimationActive={false} />
          <Line dataKey="mean" name="Twin mean" stroke={CHART.c1} dot={false} strokeWidth={2} isAnimationActive={false} />
          <Line dataKey="stress_threshold" name="Stress onset (RAW)" stroke={CHART.c3} dot={false} strokeDasharray="5 4" strokeWidth={1.3} isAnimationActive={false} />
          <Scatter dataKey="corrected" name="Corrected after reading" fill={CHART.c2} isAnimationActive={false} />
          {truth && <Line dataKey="truth" name="Simulated reference (evaluation only)" stroke={CHART.danger} dot={false} strokeWidth={1.4} strokeDasharray="2 3" isAnimationActive={false} />}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export function WaterChart({ rows, name = 'water-inputs' }: { rows: DailyRow[]; name?: string }) {
  const data = rows.map((r) => ({ day: r.day, rain: r.rain_mm, irrigation: r.applied_mm, eto: r.eto_mm }));
  return (
    <ChartFrame name={name} title="Rainfall, irrigation and reference ET" description="Daily depths in mm/day. Rain is the dataset’s realized value (revealed to the agent only after each day)."
      provenance={['simulated']} rows={data} columns={[{ key: 'day', label: 'Day' }, { key: 'rain', label: 'Rain (mm/day)' }, { key: 'irrigation', label: 'Irrigation (mm/day)' }, { key: 'eto', label: 'ET0 (mm/day)' }]}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
          <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="day" {...axisProps} label={{ value: 'Day of season', position: 'insideBottom', offset: -10, fill: CHART.axis, fontSize: 11 }} />
          <YAxis {...axisProps} width={44} label={{ value: 'mm/day', angle: -90, position: 'insideLeft', fill: CHART.axis, fontSize: 11 }} />
          <Tooltip {...tooltipStyle} />
          <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="rain" name="Rain" fill={CHART.c2} isAnimationActive={false} />
          <Bar dataKey="irrigation" name="Irrigation" fill={CHART.c1} isAnimationActive={false} />
          <Line dataKey="eto" name="ET0" stroke={CHART.c3} dot={false} strokeWidth={1.4} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export function StressChart({ rows, truth, name = 'stress' }: { rows: DailyRow[]; truth?: TruthRow[] | null; name?: string }) {
  const data = rows.map((r, i) => ({ day: r.day, est_stress: 1 - r.est_ks, depletion: r.est_depletion_fraction, true_stress: truth ? 1 - truth[i]?.true_ks : null }));
  return (
    <ChartFrame name={name} title="Estimated water stress and depletion" description="Stress = 1 − Ks (0 = none, 1 = complete). Depletion as fraction of TAW."
      provenance={truth ? ['estimated', 'truth'] : ['estimated']} rows={data}
      columns={[{ key: 'day', label: 'Day' }, { key: 'est_stress', label: 'Estimated stress (1−Ks)' }, { key: 'depletion', label: 'Est. depletion / TAW' }, ...(truth ? [{ key: 'true_stress' as const, label: 'Reference stress (evaluation only)' }] : [])]}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 18, left: 4 }}>
          <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="day" {...axisProps} label={{ value: 'Day of season', position: 'insideBottom', offset: -10, fill: CHART.axis, fontSize: 11 }} />
          <YAxis {...axisProps} width={40} domain={[0, 1]} />
          <Tooltip {...tooltipStyle} formatter={(v: number) => Number(v).toFixed(3)} />
          <Legend verticalAlign="top" height={28} wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine y={0.55} stroke={CHART.c3} strokeDasharray="4 4" />
          <Area dataKey="est_stress" name="Estimated stress" stroke={CHART.c3} fill="hsl(var(--chart-3) / 0.2)" isAnimationActive={false} />
          <Line dataKey="depletion" name="Est. depletion / TAW" stroke={CHART.c1} dot={false} isAnimationActive={false} />
          {truth && <Line dataKey="true_stress" name="Reference stress (eval.)" stroke={CHART.danger} dot={false} strokeDasharray="2 3" isAnimationActive={false} />}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
