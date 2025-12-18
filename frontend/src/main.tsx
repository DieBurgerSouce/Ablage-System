import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from '@/lib/api/query-client'
import { AuthProvider } from '@/lib/auth/AuthContext'
import { ThemeProvider } from '@/lib/theme/ThemeContext'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import type { ErrorDetails } from '@/components/ErrorBoundary'
import './index.css'

// i18n Initialisierung (muss vor App-Rendering importiert werden)
import '@/lib/i18n/config'

// Import the generated route tree
import { routeTree } from './routeTree.gen'

// Create a new router instance
const router = createRouter({ routeTree })

// Register the router instance for type safety
declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

/**
 * Global error handler for the ErrorBoundary.
 * In production, this could send errors to a monitoring service.
 */
function handleGlobalError(details: ErrorDetails): void {
  // Log error with structured data
  console.error('[GlobalErrorBoundary]', {
    error: details.error.message,
    componentStack: details.componentStack,
    timestamp: details.timestamp.toISOString(),
  })

  // TODO: In production, send to error monitoring service (e.g., Sentry)
  // if (import.meta.env.PROD) {
  //   sendToErrorMonitoring(details)
  // }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary onError={handleGlobalError}>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <RouterProvider router={router} />
          </AuthProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </StrictMode>,
)
