/**
 * Executive Dashboard Route
 *
 * Route file for executive reporting dashboard.
 */

import { createFileRoute } from '@tanstack/react-router'
import { ExecutiveDashboard } from '@/features/executive'
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary'

export const Route = createFileRoute('/executive')({
  component: ExecutiveDashboardPage,
})

function ExecutiveDashboardPage() {
  return (
    <UnifiedErrorBoundary context="general" variant="card">
      <ExecutiveDashboard />
    </UnifiedErrorBoundary>
  )
}
