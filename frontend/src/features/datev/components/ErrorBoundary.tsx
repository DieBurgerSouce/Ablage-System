/**
 * DATEV Error Boundary
 *
 * Faengt JavaScript-Fehler in Child-Komponenten ab und zeigt
 * eine benutzerfreundliche Fehler-UI mit Retry-Option.
 */

import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
    children: React.ReactNode;
    fallback?: React.ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class DATEVErrorBoundary extends React.Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
        // Nur in Development loggen
        if (import.meta.env.DEV) {
            console.error('[DATEV] Error Boundary gefangen:', error, errorInfo);
        }
    }

    handleRetry = (): void => {
        this.setState({ hasError: false, error: null });
    };

    render(): React.ReactNode {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }

            return (
                <Card className="border-destructive">
                    <CardContent className="py-10">
                        <div className="text-center">
                            <AlertTriangle className="h-12 w-12 mx-auto text-destructive mb-4" />
                            <h3 className="text-lg font-medium mb-2">
                                Ein Fehler ist aufgetreten
                            </h3>
                            <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto">
                                Bei der Anzeige dieser Komponente ist ein Fehler aufgetreten.
                                Bitte versuchen Sie es erneut oder laden Sie die Seite neu.
                            </p>
                            {import.meta.env.DEV && this.state.error && (
                                <pre className="text-xs text-left bg-muted p-4 rounded-md mb-4 overflow-x-auto max-w-lg mx-auto">
                                    {this.state.error.message}
                                </pre>
                            )}
                            <div className="flex justify-center gap-4">
                                <Button onClick={this.handleRetry}>
                                    <RefreshCw className="mr-2 h-4 w-4" />
                                    Erneut versuchen
                                </Button>
                                <Button
                                    variant="outline"
                                    onClick={() => window.location.reload()}
                                >
                                    Seite neu laden
                                </Button>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            );
        }

        return this.props.children;
    }
}
