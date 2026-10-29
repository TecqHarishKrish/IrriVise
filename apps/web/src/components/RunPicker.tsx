import { useRuns } from '@/api/hooks';
import { Select } from './ui/input';
import { shortId } from '@/lib/utils';

export function RunPicker({ scenarioId, value, onChange, filter, label = 'Saved run' }: { scenarioId?: string | null; value: string | null; onChange: (id: string) => void; filter?: (method: string) => boolean; label?: string }) {
  const runs = useRuns(scenarioId);
  const list = (runs.data ?? []).filter((r) => !filter || filter(r.method));
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor="run-picker" className="text-xs font-medium text-muted-foreground">{label}</label>
      <Select id="run-picker" value={value ?? ''} onChange={(e) => onChange(e.target.value)} disabled={!list.length} className="min-w-[16rem]">
        {!list.length && <option value="">No saved runs</option>}
        {list.map((r) => <option key={r.id} value={r.id}>{r.method_code} · {r.method_label} · season {r.season_id} ({r.split}) · seed {r.seed} · {shortId(r.id)}</option>)}
      </Select>
    </div>
  );
}
