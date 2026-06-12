/**
 * Dashboards Route - Dashboard-Editor
 *
 * Route: /dashboards/$dashboardId
 * Oeffnet ein benutzerdefiniertes Dashboard im Grid-Editor.
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import '@/features/dashboards/dashboard-grid.css';

const DashboardEditor = lazy(() =>
  import('@/features/dashboards/components/DashboardEditor').then((m) => ({
    default: m.DashboardEditor,
  }))
);

export const Route = createFileRoute('/dashboards/$dashboardId')({
  component: DashboardEditorPage,
});

function DashboardEditorPage() {
  const { dashboardId } = Route.useParams();
  return (
    <Suspense fallback={<LazyLoadFallback />}>
      <DashboardEditor dashboardId={dashboardId} />
    </Suspense>
  );
}
