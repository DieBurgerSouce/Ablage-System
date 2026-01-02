/**
 * ViewerErrorBoundary - Error Boundary fuer Dokument-Viewer
 *
 * Faengt Fehler in Viewer-Komponenten ab und verhindert App-Abstuerze.
 * Zeigt benutzerfreundliche deutsche Fehlermeldungen.
 *
 * @example
 * ```tsx
 * <ViewerErrorBoundary fileType="docx">
 *   <DocxViewer fileData={data} />
 * </ViewerErrorBoundary>
 * ```
 */

import { Component, type ReactNode, type ErrorInfo } from 'react';
import { AlertTriangle, RefreshCw, FileWarning, Bug } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface ViewerErrorBoundaryProps {
    children: ReactNode;
    /** Dateityp fuer spezifische Fehlermeldungen */
    fileType?: 'pdf' | 'docx' | 'xlsx' | 'email' | 'image' | 'unknown';
    /** Optionaler Callback bei Fehler */
    onError?: (error: Error, errorInfo: ErrorInfo) => void;
    /** Optionale Fallback-Komponente */
    fallback?: ReactNode;
    /** CSS-Klasse fuer Container */
    className?: string;
}

interface ViewerErrorBoundaryState {
    hasError: boolean;
    error: Error | null;
    errorInfo: ErrorInfo | null;
}

// ==================== German Error Messages ====================

const FILE_TYPE_MESSAGES: Record<string, { title: string; description: string }> = {
    pdf: {
        title: 'PDF konnte nicht angezeigt werden',
        description:
            'Die PDF-Datei ist möglicherweise beschädigt oder verwendet ein nicht unterstütztes Format.',
    },
    docx: {
        title: 'Word-Dokument konnte nicht angezeigt werden',
        description:
            'Das Word-Dokument konnte nicht verarbeitet werden. Möglicherweise ist die Datei beschädigt oder das Format wird nicht unterstützt.',
    },
    xlsx: {
        title: 'Excel-Tabelle konnte nicht angezeigt werden',
        description:
            'Die Excel-Datei konnte nicht geladen werden. Sehr große Dateien oder komplexe Formeln können Probleme verursachen.',
    },
    email: {
        title: 'E-Mail konnte nicht angezeigt werden',
        description:
            'Die E-Mail-Nachricht konnte nicht analysiert werden. Das Format ist möglicherweise nicht kompatibel.',
    },
    image: {
        title: 'Bild konnte nicht angezeigt werden',
        description:
            'Das Bild konnte nicht geladen werden. Möglicherweise ist die Datei beschädigt oder das Format nicht unterstützt.',
    },
    unknown: {
        title: 'Dokument konnte nicht angezeigt werden',
        description:
            'Beim Laden des Dokuments ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut.',
    },
};

// ==================== Error Boundary Component ====================

export class ViewerErrorBoundary extends Component<
    ViewerErrorBoundaryProps,
    ViewerErrorBoundaryState
> {
    constructor(props: ViewerErrorBoundaryProps) {
        super(props);
        this.state = {
            hasError: false,
            error: null,
            errorInfo: null,
        };
    }

    static getDerivedStateFromError(error: Error): Partial<ViewerErrorBoundaryState> {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
        this.setState({ errorInfo });

        // Log error for debugging (structured, no PII)
        console.error('[ViewerErrorBoundary] Viewer-Fehler aufgetreten:', {
            errorName: error.name,
            errorMessage: error.message,
            fileType: this.props.fileType,
            componentStack: errorInfo.componentStack,
        });

        // Call optional error callback
        this.props.onError?.(error, errorInfo);
    }

    handleRetry = (): void => {
        this.setState({
            hasError: false,
            error: null,
            errorInfo: null,
        });
    };

    render(): ReactNode {
        const { children, fileType = 'unknown', fallback, className } = this.props;
        const { hasError, error } = this.state;

        if (hasError) {
            // Use custom fallback if provided
            if (fallback) {
                return fallback;
            }

            const messages = FILE_TYPE_MESSAGES[fileType] ?? FILE_TYPE_MESSAGES.unknown;

            return (
                <div
                    className={cn(
                        'h-full flex items-center justify-center bg-muted/30 p-6',
                        className
                    )}
                    role="alert"
                    aria-live="assertive"
                >
                    <Card className="max-w-md w-full">
                        <CardHeader className="text-center">
                            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
                                <AlertTriangle className="h-6 w-6 text-destructive" />
                            </div>
                            <CardTitle className="text-lg">{messages.title}</CardTitle>
                            <CardDescription>{messages.description}</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {/* Error details (collapsed by default) */}
                            {error && (
                                <details className="text-sm">
                                    <summary className="cursor-pointer text-muted-foreground hover:text-foreground flex items-center gap-2">
                                        <Bug className="h-4 w-4" />
                                        Technische Details
                                    </summary>
                                    <div className="mt-2 p-3 bg-muted rounded-md font-mono text-xs overflow-auto max-h-32">
                                        <p className="font-semibold">{error.name}</p>
                                        <p className="text-muted-foreground break-all">
                                            {error.message}
                                        </p>
                                    </div>
                                </details>
                            )}

                            {/* Action buttons */}
                            <div className="flex flex-col gap-2">
                                <Button
                                    onClick={this.handleRetry}
                                    variant="default"
                                    className="w-full"
                                >
                                    <RefreshCw className="mr-2 h-4 w-4" />
                                    Erneut versuchen
                                </Button>
                                <Button
                                    variant="outline"
                                    className="w-full"
                                    onClick={() => window.location.reload()}
                                >
                                    <FileWarning className="mr-2 h-4 w-4" />
                                    Seite neu laden
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            );
        }

        return children;
    }
}

// ==================== Functional Wrapper Hook ====================

/**
 * Hook zum einfachen Wrappen von Viewer-Komponenten
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { ErrorBoundary } = useViewerErrorBoundary('xlsx');
 *   return (
 *     <ErrorBoundary>
 *       <XlsxViewer data={data} />
 *     </ErrorBoundary>
 *   );
 * }
 * ```
 */
export function useViewerErrorBoundary(fileType: ViewerErrorBoundaryProps['fileType'] = 'unknown') {
    const ErrorBoundaryWrapper = ({ children }: { children: ReactNode }) => (
        <ViewerErrorBoundary fileType={fileType}>{children}</ViewerErrorBoundary>
    );

    return { ErrorBoundary: ErrorBoundaryWrapper };
}

export default ViewerErrorBoundary;
