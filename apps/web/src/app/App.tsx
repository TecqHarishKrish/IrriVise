import * as React from 'react';
import { Route, Routes } from 'react-router-dom';
import { Layout } from './Layout';
import { LoadingBlock } from '@/components/common';
import CommandCenter from '@/pages/CommandCenter';
import ProjectsPage from '@/pages/Projects';
import DataStudio from '@/pages/DataStudio';
import DigitalTwin from '@/pages/DigitalTwin';
import Simulator from '@/pages/Simulator';
import TrainingLab from '@/pages/TrainingLab';
import CaratLab from '@/pages/CaratLab';
import Experiments from '@/pages/Experiments';
import Analytics from '@/pages/Analytics';
import Reports from '@/pages/Reports';
import SettingsPage from '@/pages/Settings';
import NotFound from '@/pages/NotFound';

export function App() {
  return (
    <React.Suspense fallback={<LoadingBlock />}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<CommandCenter />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="data" element={<DataStudio />} />
          <Route path="digital-twin" element={<DigitalTwin />} />
          <Route path="simulation" element={<Simulator />} />
          <Route path="training" element={<TrainingLab />} />
          <Route path="carat" element={<CaratLab />} />
          <Route path="experiments" element={<Experiments />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </React.Suspense>
  );
}
