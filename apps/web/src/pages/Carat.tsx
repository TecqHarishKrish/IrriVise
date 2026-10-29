import { useState } from 'react';
import {
  LineChart, Line, ReferenceLine, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { FlaskConical } from 'lucide-react';
import { Panel, Stat, Empty, ChartLegendLabel } from '../components/ui';
import { CHART_COLORS, tooltipStyle } from '../chartConfig';
import { useDaily } from '../hooks/useData';
import type { Run } from '../types';

export function Carat({ latest }: { latest?: Run }) {
  const daily = useDaily(latest?.id);
  const [page, setPage] = useState(0);

  const decisions = daily.data?.filter(d => d.observation) || [];
  const visible = decisions.slice(page * 12, (page + 1) * 12);

  const regretData = decisions.map(d => ({
    day: d.day,
    regret_before: +(d.observation!.regret_before.toFixed(3)),
    gross_voi:     +(d.observation!.gross_voi.toFixed(3)),
    net_voi:       +(d.observation!.net_voi.toFixed(3)),
    observed:       d.observation!.observe ? 1 : 0,
  }));

  const observed = decisions.filter(d => d.observation?.observe);
  const avgRegret = decisions.length
    ? decisions.reduce((s, d) => s + d.observation!.regret_before, 0) / decisions.length : 0;
  const avgNetVoi = decisions.length
    ? decisions.reduce((s, d) => s + d.observation!.net_voi, 0) / decisions.length : 0;

  return (
    <>
      <Panel title="CARAT: Counterfactual Action-Regret and Adaptive Twin Correction">
        <p className="muted">
          Estimated regret measures potential loss from deciding without current soil information.
          Value of Information (VOI) compares decisions under hypothetical readings, then subtracts a modeled observation cost.
          A sensor reading is requested only when net VOI &gt; threshold and budget remains.
        </p>
        <p className="note">
          CARAT is a <strong>proposed</strong> research method, not a pre-validated published algorithm.
          Estimated regret is an approximation. Run the CARAT controller in the Irrigation Simulator to generate traces.
        </p>
        {decisions.length > 0 && (
          <div className="stats compact">
            <Stat label="CARAT decisions" value={String(decisions.length)} sub="Days with CARAT active" />
            <Stat label="Readings requested" value={String(observed.length)} sub={`${decisions.length - observed.length} skipped (VOI below threshold)`} />
            <Stat label="Avg regret before" value={avgRegret.toFixed(3)} sub="Mean pre-decision estimated regret" />
            <Stat label="Avg net VOI" value={avgNetVoi.toFixed(3)} sub="Mean net value of observing" accent />
          </div>
        )}
      </Panel>

      {regretData.length > 0 && (
        <Panel title="Estimated regret and VOI — season timeline">
          <p className="muted">
            Green shaded lines mark days when a sensor reading was requested.
            Regret near zero normally means CARAT skips measurement.
          </p>
          <div style={{ display: 'flex', gap: 16, marginBottom: 8, flexWrap: 'wrap' }}>
            <ChartLegendLabel color={CHART_COLORS.regret}  label="Estimated regret before" />
            <ChartLegendLabel color={CHART_COLORS.voi}     label="Gross VOI" />
            <ChartLegendLabel color={CHART_COLORS.storage} label="Net VOI" />
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={regretData} margin={{ top: 5, right: 20, bottom: 10, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="day" tick={{ fontSize: 10, fill: 'var(--muted)' }}
                label={{ value: 'Day of season', position: 'insideBottom', offset: -4, fontSize: 10, fill: 'var(--muted)' }} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--muted)' }} />
              <Tooltip {...tooltipStyle} />
              {regretData.filter(d => d.observed).map(d => (
                <ReferenceLine key={d.day} x={d.day} stroke={CHART_COLORS.irrigation} strokeOpacity={0.2} strokeWidth={10} />
              ))}
              <ReferenceLine y={0} stroke="var(--line)" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="regret_before" stroke={CHART_COLORS.regret}  strokeWidth={2}   dot={false} name="Regret before" />
              <Line type="monotone" dataKey="gross_voi"     stroke={CHART_COLORS.voi}     strokeWidth={1.5} dot={false} name="Gross VOI" strokeDasharray="4 2" />
              <Line type="monotone" dataKey="net_voi"       stroke={CHART_COLORS.storage}  strokeWidth={1.5} dot={false} name="Net VOI" />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
      )}

      <Panel title="Decision trace — paginated">
        {decisions.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Day</th><th>Regret before</th><th>Gross VOI</th><th>Net VOI</th>
                    <th>Observed?</th><th>Measurement</th><th>Applied · mm</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map(d => (
                    <tr key={d.day}>
                      <td>{d.day}</td>
                      <td>{d.observation!.regret_before.toFixed(3)}</td>
                      <td>{d.observation!.gross_voi.toFixed(3)}</td>
                      <td style={{ color: d.observation!.net_voi > 0 ? CHART_COLORS.voi : 'var(--muted)' }}>
                        {d.observation!.net_voi.toFixed(3)}
                      </td>
                      <td>
                        {d.observation!.observe
                          ? <span style={{ color: CHART_COLORS.irrigation, fontWeight: 700 }}>Yes</span>
                          : <span style={{ color: 'var(--muted)' }}>No</span>}
                      </td>
                      <td>{d.observation?.measurement_mm !== undefined ? `${d.observation.measurement_mm.toFixed(1)} mm` : '—'}</td>
                      <td>{d.irrigation_mm.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <button className="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>← Previous</button>
              <span>Decisions {page * 12 + 1}–{Math.min((page + 1) * 12, decisions.length)} of {decisions.length}</span>
              <button className="ghost" disabled={(page + 1) * 12 >= decisions.length} onClick={() => setPage(page + 1)}>Next →</button>
            </div>
          </>
        ) : (
          <Empty text="Run the CARAT prototype controller to generate decision traces." icon={<FlaskConical size={32} />} />
        )}
      </Panel>
    </>
  );
}
