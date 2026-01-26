/**
 * @deprecated Diese Komponente ist veraltet. Bitte stattdessen UnifiedErrorBoundary verwenden:
 *
 * ```tsx
 * import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';
 *
 * <UnifiedErrorBoundary variant="default" context="general">
 *   {children}
 * </UnifiedErrorBoundary>
 * ```
 *
 * Migration wird empfohlen bis Q2 2026.
 */
import { Component, type ReactNode, type ErrorInfo, useState } from 'react'
import { AlertTriangle, RefreshCw, Home, Bug, Send, CheckCircle } from 'lucide-react'
import { logger } from '@/lib/logger'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'

/**
 * Error details captured by the ErrorBoundary
 * @deprecated Use UnifiedErrorBoundary from '@/components/errors/UnifiedErrorBoundary'
 */
interface ErrorDetails {
    error: Error
    errorInfo: ErrorInfo
    timestamp: Date
    componentStack: string
}

/**
 * Props for the ErrorBoundary component
 */
interface ErrorBoundaryProps {
    children: ReactNode
    /** Optional fallback component to render on error */
    fallback?: ReactNode
    /** Callback when an error is caught - useful for error reporting */
    onError?: (details: ErrorDetails) => void
    /** Whether to show detailed error info (stack traces) - default: only in development */
    showDetails?: boolean
    /** Custom error title */
    errorTitle?: string
    /** Custom error description */
    errorDescription?: string
}

interface ErrorBoundaryState {
    hasError: boolean
    error: Error | null
    errorInfo: ErrorInfo | null
}

/**
 * Send error report to backend.
 */
async function sendErrorReport(error: Error | null, errorInfo: ErrorInfo | null): Promise<boolean> {
    if (!error) return false

    try {
        const response = await fetch('/api/v1/errors', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                error: error.message,
                name: error.name,
                stack: error.stack,
                componentStack: errorInfo?.componentStack,
                timestamp: new Date().toISOString(),
                url: window.location.href,
                userAgent: navigator.userAgent,
                reported: true, // Mark as user-reported
            }),
        })
        return response.ok
    } catch {
        return false
    }
}

/**
 * Fallback UI component displayed when an error occurs.
 * Uses German language for all user-facing text.
 */
function ErrorFallback({
    error,
    errorInfo,
    onRetry,
    onGoHome,
    showDetails,
    errorTitle,
    errorDescription,
}: {
    error: Error | null
    errorInfo: ErrorInfo | null
    onRetry: () => void
    onGoHome: () => void
    showDetails: boolean
    errorTitle?: string
    errorDescription?: string
}) {
    const isDevelopment = import.meta.env.DEV
    const [reportStatus, setReportStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')

    const handleReport = async () => {
        setReportStatus('sending')
        const success = await sendErrorReport(error, errorInfo)
        setReportStatus(success ? 'sent' : 'error')
    }

    return (
        <div className="min-h-[400px] flex items-center justify-center p-6">
            <div className="w-full max-w-lg space-y-6">
                {/* Main Error Alert */}
                <Alert variant="destructive" className="border-2">
                    <AlertTriangle className="h-5 w-5" />
                    <AlertTitle className="text-lg font-semibold">
                        {errorTitle || 'Ein unerwarteter Fehler ist aufgetreten'}
                    </AlertTitle>
                    <AlertDescription className="mt-2 text-sm">
                        {errorDescription ||
                            'Die Anwendung konnte diese Aktion nicht ausführen. ' +
                            'Bitte versuchen Sie es erneut oder kehren Sie zur Startseite zurück.'}
                    </AlertDescription>
                </Alert>

                {/* Error Details (Development or if explicitly requested) */}
                {(isDevelopment || showDetails) && error && (
                    <div className="rounded-lg border border-border bg-muted/50 p-4 space-y-3">
                        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                            <Bug className="h-4 w-4" />
                            <span>Technische Details (nur für Entwickler)</span>
                        </div>

                        {/* Error Name and Message */}
                        <div className="space-y-1">
                            <p className="text-xs font-semibold text-destructive">
                                {error.name}: {error.message}
                            </p>
                        </div>

                        {/* Stack Trace */}
                        {error.stack && (
                            <details className="text-xs">
                                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                                    Stack Trace anzeigen
                                </summary>
                                <pre className={cn(
                                    "mt-2 p-3 rounded-md overflow-x-auto text-xs",
                                    "bg-background border border-border",
                                    "whitespace-pre-wrap break-words"
                                )}>
                                    {error.stack}
                                </pre>
                            </details>
                        )}

                        {/* Component Stack */}
                        {errorInfo?.componentStack && (
                            <details className="text-xs">
                                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                                    Komponenten-Stack anzeigen
                                </summary>
                                <pre className={cn(
                                    "mt-2 p-3 rounded-md overflow-x-auto text-xs",
                                    "bg-background border border-border",
                                    "whitespace-pre-wrap break-words"
                                )}>
                                    {errorInfo.componentStack}
                                </pre>
                            </details>
                        )}
                    </div>
                )}

                {/* Action Buttons */}
                <div className="flex flex-col sm:flex-row gap-3">
                    <Button
                        onClick={onRetry}
                        variant="default"
                        className="flex-1"
                    >
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Erneut versuchen
                    </Button>
                    <Button
                        onClick={onGoHome}
                        variant="outline"
                        className="flex-1"
                    >
                        <Home className="h-4 w-4 mr-2" />
                        Zur Startseite
                    </Button>
                </div>

                {/* Report Error Button */}
                <div className="pt-2 border-t border-border">
                    <Button
                        onClick={handleReport}
                        variant="ghost"
                        className="w-full text-muted-foreground hover:text-foreground"
                        disabled={reportStatus === 'sending' || reportStatus === 'sent'}
                    >
                        {reportStatus === 'idle' && (
                            <>
                                <Send className="h-4 w-4 mr-2" />
                                Fehler melden
                            </>
                        )}
                        {reportStatus === 'sending' && (
                            <>
                                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                Wird gesendet...
                            </>
                        )}
                        {reportStatus === 'sent' && (
                            <>
                                <CheckCircle className="h-4 w-4 mr-2 text-green-500" />
                                Fehler gemeldet - Danke!
                            </>
                        )}
                        {reportStatus === 'error' && (
                            <>
                                <AlertTriangle className="h-4 w-4 mr-2 text-destructive" />
                                Meldung fehlgeschlagen
                            </>
                        )}
                    </Button>
                </div>

                {/* Help Text */}
                <p className="text-xs text-muted-foreground text-center">
                    Wenn das Problem weiterhin besteht, wenden Sie sich bitte an den Support.
                </p>
            </div>
        </div>
    )
}

/**
 * ErrorBoundary Component
 *
 * Catches JavaScript errors in child component tree and displays a fallback UI.
 * All user-facing text is in German.
 *
 * @example
 * ```tsx
 * <ErrorBoundary onError={(details) => reportError(details)}>
 *   <App />
 * </ErrorBoundary>
 * ```
 *
 * @example
 * ```tsx
 * // With custom fallback
 * <ErrorBoundary fallback={<CustomErrorPage />}>
 *   <FeatureComponent />
 * </ErrorBoundary>
 * ```
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props)
        this.state = {
            hasError: false,
            error: null,
            errorInfo: null,
        }
    }

    static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
        // Update state so the next render shows the fallback UI
        return { hasError: true, error }
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
        // Update state with error info
        this.setState({ errorInfo })

        // Log error with Loki integration
        logger.error('ErrorBoundary hat einen Fehler abgefangen', error, { errorInfo })

        // Call onError callback if provided
        if (this.props.onError) {
            this.props.onError({
                error,
                errorInfo,
                timestamp: new Date(),
                componentStack: errorInfo.componentStack || '',
            })
        }
    }

    handleRetry = (): void => {
        // Reset the error state and try rendering again
        this.setState({
            hasError: false,
            error: null,
            errorInfo: null,
        })
    }

    handleGoHome = (): void => {
        // Navigate to home and reset state
        window.location.href = '/'
    }

    render(): ReactNode {
        const { hasError, error, errorInfo } = this.state
        const {
            children,
            fallback,
            showDetails = false,
            errorTitle,
            errorDescription
        } = this.props

        if (hasError) {
            // Render custom fallback if provided
            if (fallback) {
                return fallback
            }

            // Render default error UI
            return (
                <ErrorFallback
                    error={error}
                    errorInfo={errorInfo}
                    onRetry={this.handleRetry}
                    onGoHome={this.handleGoHome}
                    showDetails={showDetails}
                    errorTitle={errorTitle}
                    errorDescription={errorDescription}
                />
            )
        }

        return children
    }
}

/**
 * Hook-based error boundary wrapper for functional components.
 * Provides a convenient way to wrap components with error handling.
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   return (
 *     <WithErrorBoundary>
 *       <SomeRiskyComponent />
 *     </WithErrorBoundary>
 *   );
 * }
 * ```
 */
export function WithErrorBoundary({
    children,
    onError,
    showDetails,
    errorTitle,
    errorDescription,
}: {
    children: ReactNode
    onError?: (details: ErrorDetails) => void
    showDetails?: boolean
    errorTitle?: string
    errorDescription?: string
}) {
    return (
        <ErrorBoundary
            onError={onError}
            showDetails={showDetails}
            errorTitle={errorTitle}
            errorDescription={errorDescription}
        >
            {children}
        </ErrorBoundary>
    )
}

export type { ErrorDetails, ErrorBoundaryProps }
