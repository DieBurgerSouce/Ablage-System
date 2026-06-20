/**
 * Dashboards Route - Dashboard-Editor
 *
 * Route: /dashboards/$dashboardId
 * Oeffnet ein benutzerdefiniertes Dashboard im Grid-Editor.
 */

import { createFileRoute } from '@tanstack/react-router';
import type { ComponentType } from 'react';
import { lazyRoute } from '@/lib/lazyRoute';

import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import '@/features/dashboards/dashboard-grid.css';

const DashboardEditor = lazyRoute(() =>
  import('@/features/dashboards/components/DashboardEditor').then((m) => ({
    default: m.DashboardEditor,
  }))
) as ComponentType<{ dashboardId: string }>;

export const Route = createFileRoute('/dashboards/$dashboardId')({
  component: DashboardEditorPage,
});

function DashboardEditorPage() {
  const { dashboardId } = Route.useParams();
  return <DashboardEditor dashboardId={dashboardId} />;
}
