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
 * Send error to backend monitoring endpoint.
 * Fails silently to avoid additional errors.
 */
async function sendErrorToMonitoring(details: ErrorDetails): Promise<void> {
  try {
    await fetch('/api/v1/errors', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        error: details.error.message,
        name: details.error.name,
        stack: details.error.stack,
        componentStack: details.componentStack,
        timestamp: details.timestamp.toISOString(),
        url: window.location.href,
        userAgent: navigator.userAgent,
        // Additional context
        screenWidth: window.screen.width,
        screenHeight: window.screen.height,
        language: navigator.language,
      }),
    })
  } catch {
    // Silent fail - we don't want error reporting to cause more errors
  }
}

/**
 * Global error handler for the ErrorBoundary.
 * In production, sends errors to the backend monitoring service.
 */
function handleGlobalError(details: ErrorDetails): void {
  // Always log error with structured data for debugging
  console.error('[GlobalErrorBoundary]', {
    error: details.error.message,
    componentStack: details.componentStack,
    timestamp: details.timestamp.toISOString(),
  })

  // In production, send to error monitoring service
  if (import.meta.env.PROD) {
    sendErrorToMonitoring(details)
  }
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
