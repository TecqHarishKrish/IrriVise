import { Activity, BarChart3, Beaker, BrainCircuit, CloudSun, Droplets, FileText, FlaskConical, LayoutDashboard, Settings, Sprout } from 'lucide-react';

export const NAV = [
  { path: '/', label: 'Command Center', icon: LayoutDashboard, group: 'Overview' },
  { path: '/projects', label: 'Projects & Fields', icon: Sprout, group: 'Setup' },
  { path: '/data', label: 'Weather & Data Studio', icon: CloudSun, group: 'Setup' },
  { path: '/digital-twin', label: 'Digital Twin Studio', icon: Activity, group: 'Simulate' },
  { path: '/simulation', label: 'Irrigation Simulator', icon: Droplets, group: 'Simulate' },
  { path: '/training', label: 'Model Training Lab', icon: BrainCircuit, group: 'Learn' },
  { path: '/carat', label: 'CARAT Decision Lab', icon: FlaskConical, group: 'Learn' },
  { path: '/experiments', label: 'Experiment Benchmark', icon: Beaker, group: 'Evaluate' },
  { path: '/analytics', label: 'Insights & Analytics', icon: BarChart3, group: 'Evaluate' },
  { path: '/reports', label: 'Report & Export Center', icon: FileText, group: 'Evaluate' },
  { path: '/settings', label: 'Settings & Help', icon: Settings, group: 'System' },
] as const;
