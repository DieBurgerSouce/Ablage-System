/**
 * Dashboards Route - Neues Dashboard erstellen
 *
 * Route: /dashboards/new
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const CreateDashboard = lazy(() =>
  import('@/features/dashboards/components/CreateDashboard').then((m) => ({
    default: m.CreateDashboard,
  }))
);

export const Route = createFileRoute('/dashboards/new')({
  component: DashboardsNewPage,
});

function DashboardsNewPage() {
  return (
    <Suspense fallback={<LazyLoadFallback />}>
      <CreateDashboard />
    </Suspense>
  );
}
