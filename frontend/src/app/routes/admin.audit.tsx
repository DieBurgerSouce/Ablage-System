import { createFileRoute } from '@tanstack/react-router';
import { AuditDashboard } from '@/features/audit';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';

export const Route = createFileRoute('/admin/audit')({
  component: AuditRoute,
});

function AuditRoute() {
  return (
    <UnifiedErrorBoundary context="general" variant="card">
      <AuditDashboard />
    </UnifiedErrorBoundary>
  );
}
