import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './ui/button';

/** Keyboard-accessible day selector for replaying saved daily records. */
export function DayStepper({ day, max, onChange, label = 'Day of season' }: { day: number; max: number; onChange: (d: number) => void; label?: string }) {
  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="icon" aria-label="Previous day" disabled={day <= 1} onClick={() => onChange(day - 1)}><ChevronLeft /></Button>
      <label className="sr-only" htmlFor="day-slider">{label}</label>
      <input id="day-slider" type="range" min={1} max={max} value={day} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-[hsl(var(--primary))]" />
      <Button variant="outline" size="icon" aria-label="Next day" disabled={day >= max} onClick={() => onChange(day + 1)}><ChevronRight /></Button>
      <span className="tabular w-20 shrink-0 text-right text-sm font-medium">Day {day}/{max}</span>
    </div>
  );
}
