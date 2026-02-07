/**
 * Admin Autonomous Route
 * Route file for the Autonomous Dashboard
 */

import { createFileRoute } from '@tanstack/react-router';
import { AutonomousDashboard } from '@/features/autonomous';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';

export const Route = createFileRoute('/admin/autonomous')({
  component: AutonomousRoute,
});

function AutonomousRoute() {
  return (
    <UnifiedErrorBoundary context="general" variant="card">
      <AutonomousDashboard />
    </UnifiedErrorBoundary>
  );
}
