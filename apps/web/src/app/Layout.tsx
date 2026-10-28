import * as React from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { ChevronRight, Droplets, HelpCircle, Menu, Moon, PanelLeftClose, PanelLeftOpen, Sun, X } from 'lucide-react';
import { useHealth, useJobs } from '@/api/hooks';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { NAV } from './nav';
import { useTheme } from './theme';
import { useWorkspace } from './workspace';
import { Onboarding } from './Onboarding';

function SidebarNav({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  let group = '';
  return (
    <nav aria-label="Primary" className="flex flex-col gap-0.5 px-2 py-3">
      {NAV.map((item) => {
        const header = item.group !== group && !collapsed ? item.group : null;
        group = item.group;
        return (
          <React.Fragment key={item.path}>
            {header && <p className="mt-3 px-3 pb-1 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-sidebar-muted first:mt-0">{header}</p>}
            <NavLink
              to={item.path}
              end={item.path === '/'}
              onClick={onNavigate}
              title={collapsed ? item.label : undefined}
              className={({ isActive }) =>
                cn(
                  'group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground/85 transition-colors hover:bg-white/5 hover:text-white focus-visible:ring-offset-sidebar',
                  isActive && 'bg-sidebar-active font-medium text-white before:absolute before:left-0 before:top-1.5 before:h-[calc(100%-12px)] before:w-[3px] before:rounded-full before:bg-[#7fd6b5]',
                  collapsed && 'justify-center px-0',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon className="size-[18px] shrink-0" aria-hidden />
                  <span className={cn(collapsed && 'sr-only')}>{item.label}</span>
                  {isActive && <span className="sr-only">(current page)</span>}
                </>
              )}
            </NavLink>
          </React.Fragment>
        );
      })}
    </nav>
  );
}

function Brand({ collapsed }: { collapsed: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-3 rounded-md px-1 text-white">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/90"><Droplets className="size-5" aria-hidden /></span>
      {!collapsed && (
        <span className="leading-tight">
          <span className="block text-[0.95rem] font-semibold tracking-[0.18em]">IRRIVISE</span>
          <span className="block text-[0.7rem] text-sidebar-muted">Think Before You Water</span>
        </span>
      )}
    </Link>
  );
}

function WorkspaceSelector() {
  const ws = useWorkspace();
  if (!ws.projects.length) return <Badge variant="warning">No project yet</Badge>;
  return (
    <div className="flex min-w-0 items-center gap-2">
      <label htmlFor="ws-project" className="sr-only">Active project</label>
      <Select id="ws-project" className="h-8 w-36 truncate text-xs sm:w-44" value={ws.projectId ?? ''} onChange={(e) => ws.select(e.target.value || null)}>
        {ws.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </Select>
      <label htmlFor="ws-scenario" className="sr-only">Active scenario</label>
      <Select id="ws-scenario" className="hidden h-8 w-44 truncate text-xs md:block" value={ws.scenarioId ?? ''} onChange={(e) => ws.selectScenario(e.target.value || null)} disabled={!ws.scenarios.length}>
        {!ws.scenarios.length && <option value="">No scenario</option>}
        {ws.scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </Select>
    </div>
  );
}

export function Layout() {
  const [collapsed, setCollapsed] = React.useState(() => {
    try {
      return localStorage.getItem('irrivise.sidebar') === 'collapsed';
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const { dark, toggle } = useTheme();
  const location = useLocation();
  const current = NAV.find((n) => (n.path === '/' ? location.pathname === '/' : location.pathname.startsWith(n.path)));
  const jobs = useJobs('&status=queued,running');
  const health = useHealth();
  const ws = useWorkspace();
  const active = jobs.data?.length ?? 0;

  React.useEffect(() => {
    try {
      localStorage.setItem('irrivise.sidebar', collapsed ? 'collapsed' : 'open');
    } catch {
      /* ignore */
    }
  }, [collapsed]);
  React.useEffect(() => setMobileOpen(false), [location.pathname]);
  React.useEffect(() => {
    document.title = `${current?.label ?? 'IrriVise'} · IrriVise`;
  }, [current]);

  const apiDown = health.isError;
  const workerDown = health.data && health.data.worker.status !== 'online';

  return (
    <div className="flex min-h-screen bg-background">
      <a href="#main" className="sr-only z-50 rounded bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-3 focus:top-3">Skip to content</a>
      <aside className={cn('sticky top-0 hidden h-screen shrink-0 flex-col bg-sidebar transition-[width] duration-200 lg:flex', collapsed ? 'w-[72px]' : 'w-64')} aria-label="Sidebar">
        <div className={cn('flex h-16 items-center border-b border-white/10 px-4', collapsed && 'justify-center px-2')}><Brand collapsed={collapsed} /></div>
        <div className="flex-1 overflow-y-auto"><SidebarNav collapsed={collapsed} /></div>
        <div className="border-t border-white/10 p-2">
          <button type="button" onClick={() => setCollapsed((c) => !c)} className="flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-xs text-sidebar-muted hover:bg-white/5 hover:text-white" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            {collapsed ? <PanelLeftOpen className="size-4" /> : <><PanelLeftClose className="size-4" /> Collapse</>}
          </button>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-72 flex-col overflow-y-auto bg-sidebar shadow-xl">
            <div className="flex h-16 items-center justify-between border-b border-white/10 px-4">
              <Brand collapsed={false} />
              <button type="button" className="rounded p-1 text-white" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X className="size-5" /></button>
            </div>
            <SidebarNav collapsed={false} onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header data-app-header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-card/95 px-4 backdrop-blur sm:px-6">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu /></Button>
          <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1 text-sm text-muted-foreground md:flex">
            <Link to="/" className="hover:text-foreground">Workspace</Link>
            {ws.project && <><ChevronRight className="size-3.5" aria-hidden /><Link to="/projects" className="max-w-[10rem] truncate hover:text-foreground">{ws.project.name}</Link></>}
            <ChevronRight className="size-3.5" aria-hidden />
            <span className="truncate font-medium text-foreground" aria-current="page">{current?.label ?? 'Not found'}</span>
          </nav>
          <div className="ml-auto flex min-w-0 items-center gap-2">
            <WorkspaceSelector />
            <Link to="/training" className="hidden sm:block" aria-label={`${active} active job(s)`}>
              <Badge variant={active ? 'info' : 'outline'}>
                <span className={cn('size-1.5 rounded-full bg-current', active && 'animate-pulse-soft')} aria-hidden />
                {active} active job{active === 1 ? '' : 's'}
              </Badge>
            </Link>
            <Button asChild variant="ghost" size="icon" aria-label="Help and glossary"><Link to="/settings#help"><HelpCircle /></Link></Button>
            <Button variant="ghost" size="icon" onClick={toggle} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>{dark ? <Sun /> : <Moon />}</Button>
          </div>
        </header>
        {(apiDown || workerDown) && (
          <div role="status" className="border-b border-warning/30 bg-warning-soft px-4 py-2 text-sm sm:px-6">
            {apiDown ? 'API disconnected: cannot reach the IrriVise backend on port 8000. Data shown may be stale; actions are unavailable.'
              : `Worker ${health.data?.worker.status.replace('_', ' ')}: queued simulations and training will wait until the worker runs (python -m irrivise_api.worker).`}
          </div>
        )}
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
        <footer className="border-t px-4 py-3 text-xs text-muted-foreground sm:px-6">
          IrriVise · CARAT research prototype · All farm outcomes shown are simulated, not field measurements.
        </footer>
      </div>
      <Onboarding />
    </div>
  );
}
