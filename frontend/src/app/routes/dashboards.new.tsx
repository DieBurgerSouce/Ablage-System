/**
 * Dashboards Route - Neues Dashboard erstellen
 *
 * Route: /dashboards/new
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazyRoute } from '@/lib/lazyRoute';

const CreateDashboard = lazyRoute(() =>
  import('@/features/dashboards/components/CreateDashboard').then((m) => ({
    default: m.CreateDashboard,
  }))
);

export const Route = createFileRoute('/dashboards/new')({
  component: DashboardsNewPage,
});

function DashboardsNewPage() {
  return <CreateDashboard />;
}
