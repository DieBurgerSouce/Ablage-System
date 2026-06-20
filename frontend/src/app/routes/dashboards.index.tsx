/**
 * Dashboards Route - Eigene Dashboards (Liste)
 *
 * Route: /dashboards
 * Zeigt die Liste aller benutzerdefinierten Dashboards.
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazyRoute } from '@/lib/lazyRoute';

const DashboardList = lazyRoute(() =>
  import('@/features/dashboards/components/DashboardList').then((m) => ({
    default: m.DashboardList,
  }))
);

export const Route = createFileRoute('/dashboards/')({
  component: DashboardsIndexPage,
});

function DashboardsIndexPage() {
  return <DashboardList />;
}
