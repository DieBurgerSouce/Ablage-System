/**
 * Admin Audit-Trail Route
 *
 * Kryptografisch gesicherter Audit-Trail-Viewer
 * mit Merkle Proof Verifikation und Integritaetsbericht.
 */

import { createFileRoute } from '@tanstack/react-router';
import { AuditTrailPage } from '@/features/audit/components/AuditTrailPage';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';

export const Route = createFileRoute('/admin/audit-trail')({
  component: AuditTrailRoute,
});

function AuditTrailRoute() {
  return (
    <UnifiedErrorBoundary context="general" variant="card">
      <AuditTrailPage />
    </UnifiedErrorBoundary>
  );
}
