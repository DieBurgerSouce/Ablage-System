/**
 * Executive Dashboard Route
 *
 * Route file for executive reporting dashboard.
 */

import { createFileRoute } from '@tanstack/react-router'
import { frozenModuleGuard } from '@/lib/frozen-modules'
import { ExecutiveDashboard } from '@/features/executive'
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary'

export const Route = createFileRoute('/executive')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('ai_speculative'),
  component: ExecutiveDashboardPage,
})

function ExecutiveDashboardPage() {
  return (
    <UnifiedErrorBoundary context="general" variant="card">
      <ExecutiveDashboard />
    </UnifiedErrorBoundary>
  )
}
