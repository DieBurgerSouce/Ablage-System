/**
 * IntelligenceErrorBoundary - Spezifische Error Boundary für Intelligence-Komponenten
 *
 * Fängt Laufzeitfehler in den Enterprise Intelligence-Komponenten ab und
 * zeigt eine benutzerfreundliche Fehlermeldung mit Retry-Option.
 */

import * as React from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

interface IntelligenceErrorBoundaryProps {
  children: React.ReactNode;
  componentName: string;
  className?: string;
  compact?: boolean;
}

interface IntelligenceErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

export class IntelligenceErrorBoundary extends React.Component<
  IntelligenceErrorBoundaryProps,
  IntelligenceErrorBoundaryState
> {
  constructor(props: IntelligenceErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): IntelligenceErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    // Log error für Monitoring
    console.error(
      `[IntelligenceErrorBoundary] Fehler in ${this.props.componentName}:`,
      error,
      errorInfo
    );

    // Optional: Error Reporting an Backend
    this.reportError(error, errorInfo);
  }

  private async reportError(error: Error, errorInfo: React.ErrorInfo): Promise<void> {
    try {
      await fetch('/api/v1/errors/frontend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          component: this.props.componentName,
          error: error.message,
          stack: error.stack,
          componentStack: errorInfo.componentStack,
          timestamp: new Date().toISOString(),
          type: 'intelligence_component_error',
        }),
      });
    } catch {
      // Silently fail - don't throw in error boundary
    }
  }

  private handleRetry = (): void => {
    this.setState({ hasError: false, error: undefined });
  };

  render(): React.ReactNode {
    if (this.state.hasError) {
      const { componentName, className, compact } = this.props;

      if (compact) {
        return (
          <Card className={cn('border-destructive/50', className)}>
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-red-100 dark:bg-red-950 flex items-center justify-center">
                  <AlertTriangle className="h-5 w-5 text-red-600" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium">Fehler in {componentName}</p>
                  <p className="text-xs text-muted-foreground">
                    Komponente konnte nicht geladen werden
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={this.handleRetry}
                  aria-label="Erneut versuchen"
                >
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        );
      }

      return (
        <Card className={cn('border-destructive/50', className)}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              Fehler in {componentName}
            </CardTitle>
            <CardDescription>
              Die Komponente konnte aufgrund eines Fehlers nicht angezeigt werden.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-4 rounded-lg bg-destructive/10">
              <p className="text-sm text-muted-foreground">
                {this.state.error?.message || 'Unbekannter Fehler'}
              </p>
            </div>
            <div className="flex gap-2">
              <Button onClick={this.handleRetry} className="gap-2">
                <RefreshCw className="h-4 w-4" />
                Erneut versuchen
              </Button>
            </div>
          </CardContent>
        </Card>
      );
    }

    return this.props.children;
  }
}

/**
 * HOC zum Wrappen von Intelligence-Komponenten mit Error Boundary
 */
export function withIntelligenceErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  componentName: string
): React.FC<P & { compact?: boolean; className?: string }> {
  const WithErrorBoundary: React.FC<P & { compact?: boolean; className?: string }> = (props) => {
    return (
      <IntelligenceErrorBoundary
        componentName={componentName}
        compact={props.compact}
        className={props.className}
      >
        <WrappedComponent {...props} />
      </IntelligenceErrorBoundary>
    );
  };

  WithErrorBoundary.displayName = `WithIntelligenceErrorBoundary(${componentName})`;

  return WithErrorBoundary;
}

export default IntelligenceErrorBoundary;
