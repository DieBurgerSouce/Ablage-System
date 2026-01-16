import { createFileRoute, Outlet } from '@tanstack/react-router'
import { logger } from '@/lib/logger'
import { FinanceErrorBoundary } from '@/features/finanzen/components/FinanceErrorBoundary'

function FinanzenLayout() {
  return (
    <FinanceErrorBoundary
      onError={(error, errorInfo) => {
        // Log to monitoring service (future: Sentry, etc.)
        logger.error('[Finanzen] Unbehandelter Fehler:', error.message)
        logger.error('[Finanzen] Component Stack:', errorInfo.componentStack)
      }}
    >
      <Outlet />
    </FinanceErrorBoundary>
  )
}

export const Route = createFileRoute('/finanzen')({
  component: FinanzenLayout,
})
