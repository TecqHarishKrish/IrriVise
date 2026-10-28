import * as React from 'react';
import { useNavigate } from 'react-router-dom';
import { Sprout, TestTube2 } from 'lucide-react';
import { mutations, useInvalidate, useProjects } from '@/api/hooks';
import { errorMessage } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useWorkspace } from './workspace';

const KEY = 'irrivise.onboarding.dismissed';

/** First-launch guide: shown only when no project exists and the user has not dismissed it. */
export function Onboarding() {
  const projects = useProjects(true);
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const navigate = useNavigate();
  const ws = useWorkspace();
  const refresh = useInvalidate();

  React.useEffect(() => {
    let dismissed = false;
    try {
      dismissed = localStorage.getItem(KEY) === '1';
    } catch {
      /* ignore */
    }
    if (projects.data && projects.data.length === 0 && !dismissed) setOpen(true);
  }, [projects.data]);

  const close = () => {
    try {
      localStorage.setItem(KEY, '1');
    } catch {
      /* ignore */
    }
    setOpen(false);
  };

  const explore = async () => {
    setBusy(true);
    setError(null);
    try {
      const { project, scenario } = await mutations.sampleProject();
      ws.select(project.id, scenario.id);
      refresh('projects', 'scenarios');
      close();
      navigate('/simulation?start=fixed_schedule');
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? setOpen(true) : close())}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Welcome to IrriVise</DialogTitle>
          <DialogDescription>
            Think before you water: simulate a field, estimate soil water with a digital twin, and test whether CARAT’s “observe only when it changes the decision” rule
            helps — honestly, against baselines.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" onClick={explore} disabled={busy} className="flex flex-col gap-2 rounded-lg border p-4 text-left transition-colors hover:border-primary hover:bg-secondary disabled:opacity-60">
            <TestTube2 className="size-5 text-primary" aria-hidden />
            <span className="font-semibold">Explore sample field</span>
            <span className="text-xs text-muted-foreground">Creates a maize field on sandy loam with 20 years of <strong>synthetic demonstration weather</strong> (not field measurements), then opens the simulator.</span>
          </button>
          <button type="button" onClick={() => { close(); navigate('/projects?new=1'); }} className="flex flex-col gap-2 rounded-lg border p-4 text-left transition-colors hover:border-primary hover:bg-secondary">
            <Sprout className="size-5 text-primary" aria-hidden />
            <span className="font-semibold">Create my field</span>
            <span className="text-xs text-muted-foreground">Set location, crop, soil, planting date, water and observation budgets. Attach sample, uploaded or NASA POWER weather.</span>
          </button>
        </div>
        {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
        <div className="mt-4 flex justify-end"><Button variant="ghost" onClick={close}>Skip for now</Button></div>
      </DialogContent>
    </Dialog>
  );
}
