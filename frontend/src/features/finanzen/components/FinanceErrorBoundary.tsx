/**
 * FinanceErrorBoundary - Enterprise-grade Error Handling fuer Finanzen-Modul
 *
 * Features:
 * - Differenzierte Fehlerdarstellung (Network, 404, 500, Validation)
 * - Retry-Funktionalitaet
 * - Error-Logging
 * - Fallback UI mit hilfreichen Aktionen
 */

import { Component, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw, Home, WifiOff, FileQuestion, ServerCrash, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

// ==================== ERROR TYPES ====================

export type FinanceErrorType = 'network' | 'not_found' | 'server_error' | 'validation' | 'unknown'

export interface FinanceError {
  type: FinanceErrorType
  message: string
  statusCode?: number
  details?: string
  retryable: boolean
}

// ==================== ERROR DETECTION ====================

export function classifyError(error: unknown): FinanceError {
  // Network Error (offline, timeout, CORS)
  if (error instanceof TypeError && error.message.includes('fetch')) {
    return {
      type: 'network',
      message: 'Netzwerkfehler',
      details: 'Die Verbindung zum Server konnte nicht hergestellt werden. Bitte ueberpruefen Sie Ihre Internetverbindung.',
      retryable: true,
    }
  }

  // Axios/Fetch Error with response
  if (typeof error === 'object' && error !== null) {
    const err = error as Record<string, unknown>

    // Check for status code
    const status = (err.status as number) || (err.statusCode as number) || ((err.response as Record<string, unknown>)?.status as number)

    if (status === 404) {
      return {
        type: 'not_found',
        message: 'Nicht gefunden',
        statusCode: 404,
        details: 'Das angeforderte Dokument oder die Ressource wurde nicht gefunden.',
        retryable: false,
      }
    }

    if (status === 400 || status === 422) {
      return {
        type: 'validation',
        message: 'Validierungsfehler',
        statusCode: status,
        details: (err.message as string) || 'Die eingegebenen Daten sind ungueltig.',
        retryable: false,
      }
    }

    if (status === 401 || status === 403) {
      return {
        type: 'validation',
        message: 'Zugriff verweigert',
        statusCode: status,
        details: 'Sie haben keine Berechtigung fuer diese Aktion.',
        retryable: false,
      }
    }

    if (status >= 500) {
      return {
        type: 'server_error',
        message: 'Serverfehler',
        statusCode: status,
        details: 'Ein interner Serverfehler ist aufgetreten. Bitte versuchen Sie es spaeter erneut oder kontaktieren Sie den Support.',
        retryable: true,
      }
    }

    // Generic error with message
    if (err.message) {
      return {
        type: 'unknown',
        message: 'Fehler',
        details: err.message as string,
        retryable: true,
      }
    }
  }

  // Unknown error
  return {
    type: 'unknown',
    message: 'Unbekannter Fehler',
    details: 'Ein unerwarteter Fehler ist aufgetreten.',
    retryable: true,
  }
}

// ==================== ERROR ICONS ====================

function getErrorIcon(type: FinanceErrorType) {
  switch (type) {
    case 'network':
      return <WifiOff className="h-12 w-12 text-orange-500" />
    case 'not_found':
      return <FileQuestion className="h-12 w-12 text-blue-500" />
    case 'server_error':
      return <ServerCrash className="h-12 w-12 text-red-500" />
    case 'validation':
      return <AlertCircle className="h-12 w-12 text-yellow-500" />
    default:
      return <AlertTriangle className="h-12 w-12 text-gray-500" />
  }
}

function getErrorColor(type: FinanceErrorType): string {
  switch (type) {
    case 'network':
      return 'border-orange-500/50 bg-orange-500/10'
    case 'not_found':
      return 'border-blue-500/50 bg-blue-500/10'
    case 'server_error':
      return 'border-red-500/50 bg-red-500/10'
    case 'validation':
      return 'border-yellow-500/50 bg-yellow-500/10'
    default:
      return 'border-gray-500/50 bg-gray-500/10'
  }
}

// ==================== ERROR CARD COMPONENT ====================

interface FinanceErrorCardProps {
  error: FinanceError
  onRetry?: () => void
  onGoHome?: () => void
  showDetails?: boolean
}

export function FinanceErrorCard({ error, onRetry, onGoHome, showDetails = true }: FinanceErrorCardProps) {
  return (
    <Card className={`max-w-md mx-auto ${getErrorColor(error.type)}`}>
      <CardHeader className="text-center">
        <div className="flex justify-center mb-4">
          {getErrorIcon(error.type)}
        </div>
        <CardTitle className="text-xl">
          {error.message}
          {error.statusCode && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              (Code: {error.statusCode})
            </span>
          )}
        </CardTitle>
        {showDetails && error.details && (
          <CardDescription className="text-sm mt-2">
            {error.details}
          </CardDescription>
        )}
      </CardHeader>

      <CardFooter className="flex justify-center gap-3">
        {error.retryable && onRetry && (
          <Button onClick={onRetry} variant="default" className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Erneut versuchen
          </Button>
        )}
        {onGoHome && (
          <Button onClick={onGoHome} variant="outline" className="gap-2">
            <Home className="h-4 w-4" />
            Zur Uebersicht
          </Button>
        )}
      </CardFooter>
    </Card>
  )
}

// ==================== INLINE ERROR ALERT ====================

interface FinanceErrorAlertProps {
  error: FinanceError
  onRetry?: () => void
  className?: string
}

export function FinanceErrorAlert({ error, onRetry, className = '' }: FinanceErrorAlertProps) {
  const variant = error.type === 'server_error' ? 'destructive' : 'default'

  return (
    <Alert variant={variant} className={className}>
      {getErrorIcon(error.type)}
      <AlertTitle>{error.message}</AlertTitle>
      <AlertDescription className="flex items-center justify-between">
        <span>{error.details}</span>
        {error.retryable && onRetry && (
          <Button size="sm" variant="outline" onClick={onRetry} className="ml-4 gap-1">
            <RefreshCw className="h-3 w-3" />
            Retry
          </Button>
        )}
      </AlertDescription>
    </Alert>
  )
}

// ==================== ERROR BOUNDARY CLASS ====================

interface FinanceErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void
  onReset?: () => void
}

interface FinanceErrorBoundaryState {
  hasError: boolean
  error: FinanceError | null
  originalError: Error | null
}

export class FinanceErrorBoundary extends Component<FinanceErrorBoundaryProps, FinanceErrorBoundaryState> {
  constructor(props: FinanceErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null, originalError: null }
  }

  static getDerivedStateFromError(error: Error): FinanceErrorBoundaryState {
    return {
      hasError: true,
      error: classifyError(error),
      originalError: error,
    }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log error for monitoring
    console.error('[FinanceErrorBoundary] Error caught:', error)
    console.error('[FinanceErrorBoundary] Component stack:', errorInfo.componentStack)

    // Call custom error handler if provided
    this.props.onError?.(error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, originalError: null })
    this.props.onReset?.()
  }

  handleGoHome = () => {
    window.location.href = '/finanzen'
  }

  render() {
    if (this.state.hasError) {
      // Custom fallback provided
      if (this.props.fallback) {
        return this.props.fallback
      }

      // Default error UI
      return (
        <div className="flex items-center justify-center min-h-[400px] p-8">
          <FinanceErrorCard
            error={this.state.error!}
            onRetry={this.state.error?.retryable ? this.handleReset : undefined}
            onGoHome={this.handleGoHome}
          />
        </div>
      )
    }

    return this.props.children
  }
}

// ==================== HOOK FOR QUERY ERRORS ====================

import { useNavigate } from '@tanstack/react-router'

interface UseFinanceErrorOptions {
  onRetry?: () => void
  navigateOnNotFound?: string
}

export function useFinanceError(error: unknown, options: UseFinanceErrorOptions = {}) {
  const navigate = useNavigate()
  const classifiedError = error ? classifyError(error) : null

  const handleRetry = () => {
    options.onRetry?.()
  }

  const handleGoHome = () => {
    navigate({ to: '/finanzen' })
  }

  const handleNavigateBack = () => {
    if (options.navigateOnNotFound && classifiedError?.type === 'not_found') {
      navigate({ to: options.navigateOnNotFound })
    } else {
      navigate({ to: '/finanzen' })
    }
  }

  return {
    error: classifiedError,
    isNetworkError: classifiedError?.type === 'network',
    isNotFound: classifiedError?.type === 'not_found',
    isServerError: classifiedError?.type === 'server_error',
    isValidationError: classifiedError?.type === 'validation',
    isRetryable: classifiedError?.retryable ?? false,
    handleRetry,
    handleGoHome,
    handleNavigateBack,
  }
}

export default FinanceErrorBoundary
