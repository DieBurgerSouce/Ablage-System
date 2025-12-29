import { createFileRoute, Outlet } from '@tanstack/react-router'
import { FinanceErrorBoundary } from '@/features/finanzen/components/FinanceErrorBoundary'

function FinanzenLayout() {
  return (
    <FinanceErrorBoundary
      onError={(error, errorInfo) => {
        // Log to monitoring service (future: Sentry, etc.)
        console.error('[Finanzen] Unhandled error:', error.message)
        console.error('[Finanzen] Component stack:', errorInfo.componentStack)
      }}
    >
      <Outlet />
    </FinanceErrorBoundary>
  )
}

export const Route = createFileRoute('/finanzen')({
  component: FinanzenLayout,
})
