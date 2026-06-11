/**
 * UnifiedErrorBoundary - Enterprise-grade Error Boundary
 *
 * Consolidates functionality from:
 * - ErrorBoundary (components/)
 * - ViewerErrorBoundary (components/errors/)
 * - FinanceErrorBoundary (features/finanzen/)
 * - IntelligenceErrorBoundary (features/privat/)
 * - DATEVErrorBoundary (features/datev/)
 *
 * Features:
 * - Multiple display variants (default, compact, inline, card)
 * - Context-aware error messages (viewer, finance, datev, intelligence, general)
 * - Error classification (network, not_found, server_error, validation, unknown)
 * - Error reporting to backend
 * - Retry and navigation options
 * - German language UI
 * - WCAG 2.1 AA accessibility
 */

import { Component, type ReactNode, type ErrorInfo, useState, useCallback } from 'react';
import {
  AlertTriangle,
  RefreshCw,
  Home,
  Bug,
  Send,
  CheckCircle,
  WifiOff,
  FileQuestion,
  ServerCrash,
  AlertCircle,
  FileWarning,
} from 'lucide-react';
import { logger } from '@/lib/logger';
import { Button } from '@/components/ui/button';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

// ==================== TYPES ====================

export type ErrorBoundaryVariant = 'default' | 'compact' | 'inline' | 'card';

export type ErrorBoundaryContext =
  | 'viewer'
  | 'finance'
  | 'datev'
  | 'intelligence'
  | 'general';

export type ErrorType = 'network' | 'not_found' | 'server_error' | 'validation' | 'unknown';

export interface ClassifiedError {
  type: ErrorType;
  message: string;
  statusCode?: number;
  details?: string;
  retryable: boolean;
}

export interface ErrorDetails {
  error: Error;
  errorInfo: ErrorInfo;
  timestamp: Date;
  componentStack: string;
  classifiedError: ClassifiedError;
}

export interface UnifiedErrorBoundaryProps {
  children: ReactNode;
  /** Display variant */
  variant?: ErrorBoundaryVariant;
  /** Context for error messages */
  context?: ErrorBoundaryContext;
  /** Component name for logging (used with intelligence context) */
  componentName?: string;
  /** File type for viewer context */
  fileType?: 'pdf' | 'docx' | 'xlsx' | 'email' | 'image' | 'unknown';
  /** Custom fallback component */
  fallback?: ReactNode;
  /** Callback when error is caught */
  onError?: (details: ErrorDetails) => void;
  /** Callback when reset is triggered */
  onReset?: () => void;
  /** Show detailed error info (stack traces) */
  showDetails?: boolean;
  /** Report errors to backend */
  reportToBackend?: boolean;
  /** Custom error title */
  errorTitle?: string;
  /** Custom error description */
  errorDescription?: string;
  /** Custom "go home" URL */
  homeUrl?: string;
  /** CSS class for container */
  className?: string;
}

interface UnifiedErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  classifiedError: ClassifiedError | null;
}

// ==================== ERROR CLASSIFICATION ====================

function classifyError(error: unknown): ClassifiedError {
  // Network Error (offline, timeout, CORS)
  if (error instanceof TypeError && error.message.includes('fetch')) {
    return {
      type: 'network',
      message: 'Netzwerkfehler',
      details: 'Die Verbindung zum Server konnte nicht hergestellt werden. Bitte überprüfen Sie Ihre Internetverbindung.',
      retryable: true,
    };
  }

  // Axios/Fetch Error with response
  if (typeof error === 'object' && error !== null) {
    const err = error as Record<string, unknown>;
    const status = (err.status as number) || (err.statusCode as number) ||
      ((err.response as Record<string, unknown>)?.status as number);

    if (status === 404) {
      return {
        type: 'not_found',
        message: 'Nicht gefunden',
        statusCode: 404,
        details: 'Das angeforderte Dokument oder die Ressource wurde nicht gefunden.',
        retryable: false,
      };
    }

    if (status === 400 || status === 422) {
      return {
        type: 'validation',
        message: 'Validierungsfehler',
        statusCode: status,
        details: (err.message as string) || 'Die eingegebenen Daten sind ungültig.',
        retryable: false,
      };
    }

    if (status === 401 || status === 403) {
      return {
        type: 'validation',
        message: 'Zugriff verweigert',
        statusCode: status,
        details: 'Sie haben keine Berechtigung für diese Aktion.',
        retryable: false,
      };
    }

    if (status >= 500) {
      return {
        type: 'server_error',
        message: 'Serverfehler',
        statusCode: status,
        details: 'Ein interner Serverfehler ist aufgetreten. Bitte versuchen Sie es später erneut.',
        retryable: true,
      };
    }

    if (err.message) {
      return {
        type: 'unknown',
        message: 'Fehler',
        details: err.message as string,
        retryable: true,
      };
    }
  }

  return {
    type: 'unknown',
    message: 'Unbekannter Fehler',
    details: 'Ein unerwarteter Fehler ist aufgetreten.',
    retryable: true,
  };
}

// ==================== CONTEXT-SPECIFIC MESSAGES ====================

const VIEWER_MESSAGES: Record<string, { title: string; description: string }> = {
  pdf: {
    title: 'PDF konnte nicht angezeigt werden',
    description: 'Die PDF-Datei ist möglicherweise beschädigt oder verwendet ein nicht unterstütztes Format.',
  },
  docx: {
    title: 'Word-Dokument konnte nicht angezeigt werden',
    description: 'Das Word-Dokument konnte nicht verarbeitet werden.',
  },
  xlsx: {
    title: 'Excel-Tabelle konnte nicht angezeigt werden',
    description: 'Die Excel-Datei konnte nicht geladen werden. Sehr große Dateien können Probleme verursachen.',
  },
  email: {
    title: 'E-Mail konnte nicht angezeigt werden',
    description: 'Die E-Mail-Nachricht konnte nicht analysiert werden.',
  },
  image: {
    title: 'Bild konnte nicht angezeigt werden',
    description: 'Das Bild konnte nicht geladen werden.',
  },
  unknown: {
    title: 'Dokument konnte nicht angezeigt werden',
    description: 'Beim Laden des Dokuments ist ein Fehler aufgetreten.',
  },
};

const CONTEXT_HOME_URLS: Record<ErrorBoundaryContext, string> = {
  viewer: '/',
  finance: '/finanzen',
  datev: '/datev',
  intelligence: '/privat',
  general: '/',
};

// ==================== ERROR ICONS ====================

function getErrorIcon(type: ErrorType, className: string = 'h-6 w-6') {
  switch (type) {
    case 'network':
      return <WifiOff className={cn(className, 'text-orange-500')} />;
    case 'not_found':
      return <FileQuestion className={cn(className, 'text-blue-500')} />;
    case 'server_error':
      return <ServerCrash className={cn(className, 'text-red-500')} />;
    case 'validation':
      return <AlertCircle className={cn(className, 'text-yellow-500')} />;
    default:
      return <AlertTriangle className={cn(className, 'text-gray-500')} />;
  }
}

// ==================== ERROR REPORTING ====================

async function sendErrorReport(
  error: Error | null,
  errorInfo: ErrorInfo | null,
  context: ErrorBoundaryContext,
  componentName?: string
): Promise<boolean> {
  if (!error) return false;

  try {
    const response = await fetch('/api/v1/errors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        error: error.message,
        name: error.name,
        stack: error.stack,
        componentStack: errorInfo?.componentStack,
        timestamp: new Date().toISOString(),
        url: window.location.href,
        userAgent: navigator.userAgent,
        context,
        componentName,
        reported: true,
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

// ==================== FALLBACK COMPONENTS ====================

interface FallbackProps {
  error: Error | null;
  errorInfo: ErrorInfo | null;
  classifiedError: ClassifiedError | null;
  onRetry: () => void;
  onGoHome: () => void;
  variant: ErrorBoundaryVariant;
  context: ErrorBoundaryContext;
  componentName?: string;
  fileType?: string;
  showDetails: boolean;
  reportToBackend: boolean;
  errorTitle?: string;
  errorDescription?: string;
  className?: string;
}

function ErrorFallback({
  error,
  errorInfo,
  classifiedError,
  onRetry,
  onGoHome,
  variant,
  context,
  componentName,
  fileType,
  showDetails,
  reportToBackend,
  errorTitle,
  errorDescription,
  className,
}: FallbackProps) {
  const isDevelopment = import.meta.env.DEV;
  const [reportStatus, setReportStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');

  const handleReport = useCallback(async () => {
    setReportStatus('sending');
    const success = await sendErrorReport(error, errorInfo, context, componentName);
    setReportStatus(success ? 'sent' : 'error');
  }, [error, errorInfo, context, componentName]);

  // Get context-specific messages
  const getTitle = () => {
    if (errorTitle) return errorTitle;
    if (context === 'viewer' && fileType) {
      return VIEWER_MESSAGES[fileType]?.title ?? VIEWER_MESSAGES.unknown.title;
    }
    if (context === 'intelligence' && componentName) {
      return `Fehler in ${componentName}`;
    }
    return classifiedError?.message ?? 'Ein unerwarteter Fehler ist aufgetreten';
  };

  const getDescription = () => {
    if (errorDescription) return errorDescription;
    if (context === 'viewer' && fileType) {
      return VIEWER_MESSAGES[fileType]?.description ?? VIEWER_MESSAGES.unknown.description;
    }
    return classifiedError?.details ?? 'Die Anwendung konnte diese Aktion nicht ausführen.';
  };

  const title = getTitle();
  const description = getDescription();
  const canRetry = classifiedError?.retryable ?? true;

  // Compact variant
  if (variant === 'compact') {
    return (
      <Card className={cn('border-destructive/50', className)}>
        <CardContent className="p-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-red-100 dark:bg-red-950 flex items-center justify-center flex-shrink-0">
              {getErrorIcon(classifiedError?.type ?? 'unknown', 'h-5 w-5')}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{title}</p>
              <p className="text-xs text-muted-foreground truncate">{description}</p>
            </div>
            {canRetry && (
              <Button variant="ghost" size="sm" onClick={onRetry} aria-label="Erneut versuchen">
                <RefreshCw className="h-4 w-4" />
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Inline variant
  if (variant === 'inline') {
    return (
      <Alert variant="destructive" className={className} role="alert" aria-live="assertive">
        {getErrorIcon(classifiedError?.type ?? 'unknown', 'h-4 w-4')}
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription className="flex items-center justify-between">
          <span>{description}</span>
          {canRetry && (
            <Button size="sm" variant="outline" onClick={onRetry} className="ml-4 gap-1">
              <RefreshCw className="h-3 w-3" />
              Wiederholen
            </Button>
          )}
        </AlertDescription>
      </Alert>
    );
  }

  // Card variant
  if (variant === 'card') {
    return (
      <div
        className={cn('h-full flex items-center justify-center bg-muted/30 p-6', className)}
        role="alert"
        aria-live="assertive"
      >
        <Card className="max-w-md w-full">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
              {getErrorIcon(classifiedError?.type ?? 'unknown')}
            </div>
            <CardTitle className="text-lg">{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {(isDevelopment || showDetails) && error && (
              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground flex items-center gap-2">
                  <Bug className="h-4 w-4" />
                  Technische Details
                </summary>
                <div className="mt-2 p-3 bg-muted rounded-md font-mono text-xs overflow-auto max-h-32">
                  <p className="font-semibold">{error.name}</p>
                  <p className="text-muted-foreground break-all">{error.message}</p>
                </div>
              </details>
            )}
            <div className="flex flex-col gap-2">
              {canRetry && (
                <Button onClick={onRetry} variant="default" className="w-full">
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Erneut versuchen
                </Button>
              )}
              <Button variant="outline" className="w-full" onClick={() => window.location.reload()}>
                <FileWarning className="mr-2 h-4 w-4" />
                Seite neu laden
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Default variant (full)
  return (
    <div
      className={cn('min-h-[400px] flex items-center justify-center p-6', className)}
      role="alert"
      aria-live="assertive"
    >
      <div className="w-full max-w-lg space-y-6">
        <Alert variant="destructive" className="border-2">
          {getErrorIcon(classifiedError?.type ?? 'unknown', 'h-5 w-5')}
          <AlertTitle className="text-lg font-semibold">{title}</AlertTitle>
          <AlertDescription className="mt-2 text-sm">{description}</AlertDescription>
        </Alert>

        {(isDevelopment || showDetails) && error && (
          <div className="rounded-lg border border-border bg-muted/50 p-4 space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Bug className="h-4 w-4" />
              <span>Technische Details (nur für Entwickler)</span>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-semibold text-destructive">
                {error.name}: {error.message}
              </p>
            </div>
            {error.stack && (
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                  Stack Trace anzeigen
                </summary>
                <pre className={cn(
                  'mt-2 p-3 rounded-md overflow-x-auto text-xs',
                  'bg-background border border-border',
                  'whitespace-pre-wrap break-words'
                )}>
                  {error.stack}
                </pre>
              </details>
            )}
            {errorInfo?.componentStack && (
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                  Komponenten-Stack anzeigen
                </summary>
                <pre className={cn(
                  'mt-2 p-3 rounded-md overflow-x-auto text-xs',
                  'bg-background border border-border',
                  'whitespace-pre-wrap break-words'
                )}>
                  {errorInfo.componentStack}
                </pre>
              </details>
            )}
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-3">
          {canRetry && (
            <Button onClick={onRetry} variant="default" className="flex-1">
              <RefreshCw className="h-4 w-4 mr-2" />
              Erneut versuchen
            </Button>
          )}
          <Button onClick={onGoHome} variant="outline" className="flex-1">
            <Home className="h-4 w-4 mr-2" />
            Zur Startseite
          </Button>
        </div>

        {reportToBackend && (
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
        )}

        <p className="text-xs text-muted-foreground text-center">
          Wenn das Problem weiterhin besteht, wenden Sie sich bitte an den Support.
        </p>
      </div>
    </div>
  );
}

// ==================== ERROR BOUNDARY CLASS ====================

export class UnifiedErrorBoundary extends Component<UnifiedErrorBoundaryProps, UnifiedErrorBoundaryState> {
  constructor(props: UnifiedErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      classifiedError: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<UnifiedErrorBoundaryState> {
    return {
      hasError: true,
      error,
      classifiedError: classifyError(error),
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    const classifiedError = classifyError(error);
    this.setState({ errorInfo, classifiedError });

    const { context = 'general', componentName, reportToBackend = false, onError } = this.props;

    // Log error
    logger.error(`[UnifiedErrorBoundary:${context}] Fehler abgefangen`, error, {
      componentName,
      componentStack: errorInfo.componentStack,
      errorType: classifiedError.type,
    });

    // Auto-report if enabled
    if (reportToBackend) {
      sendErrorReport(error, errorInfo, context, componentName);
    }

    // Call onError callback if provided
    if (onError) {
      onError({
        error,
        errorInfo,
        timestamp: new Date(),
        componentStack: errorInfo.componentStack || '',
        classifiedError,
      });
    }
  }

  handleRetry = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      classifiedError: null,
    });
    this.props.onReset?.();
  };

  handleGoHome = (): void => {
    const { context = 'general', homeUrl } = this.props;
    window.location.href = homeUrl ?? CONTEXT_HOME_URLS[context];
  };

  render(): ReactNode {
    const { hasError, error, errorInfo, classifiedError } = this.state;
    const {
      children,
      variant = 'default',
      context = 'general',
      componentName,
      fileType,
      fallback,
      showDetails = false,
      reportToBackend = false,
      errorTitle,
      errorDescription,
      className,
    } = this.props;

    if (hasError) {
      if (fallback) {
        return fallback;
      }

      return (
        <ErrorFallback
          error={error}
          errorInfo={errorInfo}
          classifiedError={classifiedError}
          onRetry={this.handleRetry}
          onGoHome={this.handleGoHome}
          variant={variant}
          context={context}
          componentName={componentName}
          fileType={fileType}
          showDetails={showDetails}
          reportToBackend={reportToBackend}
          errorTitle={errorTitle}
          errorDescription={errorDescription}
          className={className}
        />
      );
    }

    return children;
  }
}

// ==================== FUNCTIONAL WRAPPERS ====================

/**
 * Functional wrapper for UnifiedErrorBoundary
 */
export function WithUnifiedErrorBoundary({
  children,
  ...props
}: UnifiedErrorBoundaryProps) {
  return <UnifiedErrorBoundary {...props}>{children}</UnifiedErrorBoundary>;
}

/**
 * HOC to wrap components with UnifiedErrorBoundary
 */
export function withUnifiedErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  boundaryProps: Omit<UnifiedErrorBoundaryProps, 'children'>
): React.FC<P> {
  const WithErrorBoundary: React.FC<P> = (props) => (
    <UnifiedErrorBoundary {...boundaryProps}>
      <WrappedComponent {...props} />
    </UnifiedErrorBoundary>
  );

  WithErrorBoundary.displayName = `WithUnifiedErrorBoundary(${WrappedComponent.displayName || WrappedComponent.name || 'Component'})`;

  return WithErrorBoundary;
}

// ==================== SPECIALIZED EXPORTS (for migration) ====================

/**
 * ViewerErrorBoundary replacement
 * @deprecated Use UnifiedErrorBoundary with context="viewer" instead
 */
export function ViewerErrorBoundaryCompat({
  children,
  fileType = 'unknown',
  onError,
  className,
}: {
  children: ReactNode;
  fileType?: 'pdf' | 'docx' | 'xlsx' | 'email' | 'image' | 'unknown';
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  className?: string;
}) {
  return (
    <UnifiedErrorBoundary
      context="viewer"
      variant="card"
      fileType={fileType}
      className={className}
      onError={onError ? (details) => onError(details.error, details.errorInfo) : undefined}
    >
      {children}
    </UnifiedErrorBoundary>
  );
}

/**
 * FinanceErrorBoundary replacement
 * @deprecated Use UnifiedErrorBoundary with context="finance" instead
 */
export function FinanceErrorBoundaryCompat({
  children,
  fallback,
  onError,
  onReset,
}: {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  onReset?: () => void;
}) {
  return (
    <UnifiedErrorBoundary
      context="finance"
      variant="card"
      fallback={fallback}
      homeUrl="/finanzen"
      onError={onError ? (details) => onError(details.error, details.errorInfo) : undefined}
      onReset={onReset}
    >
      {children}
    </UnifiedErrorBoundary>
  );
}

/**
 * IntelligenceErrorBoundary replacement
 * @deprecated Use UnifiedErrorBoundary with context="intelligence" instead
 */
export function IntelligenceErrorBoundaryCompat({
  children,
  componentName,
  compact = false,
  className,
}: {
  children: ReactNode;
  componentName: string;
  compact?: boolean;
  className?: string;
}) {
  return (
    <UnifiedErrorBoundary
      context="intelligence"
      variant={compact ? 'compact' : 'card'}
      componentName={componentName}
      className={className}
      reportToBackend
    >
      {children}
    </UnifiedErrorBoundary>
  );
}

/**
 * DATEVErrorBoundary replacement
 * @deprecated Use UnifiedErrorBoundary with context="datev" instead
 */
export function DATEVErrorBoundaryCompat({
  children,
  fallback,
}: {
  children: ReactNode;
  fallback?: ReactNode;
}) {
  return (
    <UnifiedErrorBoundary
      context="datev"
      variant="card"
      fallback={fallback}
      homeUrl="/datev"
    >
      {children}
    </UnifiedErrorBoundary>
  );
}

export default UnifiedErrorBoundary;

// Re-export types
export type { ErrorDetails as UnifiedErrorDetails };
