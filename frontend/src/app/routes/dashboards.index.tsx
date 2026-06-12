/**
 * Dashboards Route - Eigene Dashboards (Liste)
 *
 * Route: /dashboards
 * Zeigt die Liste aller benutzerdefinierten Dashboards.
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const DashboardList = lazy(() =>
  import('@/features/dashboards/components/DashboardList').then((m) => ({
    default: m.DashboardList,
  }))
);

export const Route = createFileRoute('/dashboards/')({
  component: DashboardsIndexPage,
});

function DashboardsIndexPage() {
  return (
    <Suspense fallback={<LazyLoadFallback />}>
      <DashboardList />
    </Suspense>
  );
}
