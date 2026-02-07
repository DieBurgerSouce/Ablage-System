/**
 * Alert Center Admin Route
 *
 * Route fuer das zentrale Alert-Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { AlertCenter } from '@/features/alerts';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';

export const Route = createFileRoute('/admin/alerts')({
  component: AlertsRoute,
});

function AlertsRoute() {
  return (
    <UnifiedErrorBoundary context="general" variant="card">
      <AlertCenter />
    </UnifiedErrorBoundary>
  );
}
