import { useState, useEffect, useRef } from 'react';
import {
    Loader2,
    AlertTriangle,
    ZoomIn,
    ZoomOut,
    RotateCcw,
    FileText,
    X,
} from 'lucide-react';
import {
    Dialog,
    DialogContent,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { apiClient } from '@/lib/api/client';

/**
 * Hook um Dokument-Preview mit Auth-Token zu laden.
 */
function useAuthenticatedPreview(documentId: string | null) {
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [mimeType, setMimeType] = useState<string | null>(null);

    useEffect(() => {
        if (!documentId) {
            setBlobUrl(null);
            setError(null);
            setMimeType(null);
            return;
        }

        let objectUrl: string | null = null;
        let cancelled = false;

        async function loadPreview() {
            setIsLoading(true);
            setError(null);

            try {
                const response = await apiClient.get(`/documents/${documentId}/preview`, {
                    responseType: 'blob',
                });

                if (cancelled) return;

                const blob = response.data as Blob;
                setMimeType(blob.type);
                objectUrl = URL.createObjectURL(blob);
                setBlobUrl(objectUrl);
            } catch (err) {
                if (cancelled) return;
                const message =
                    err instanceof Error ? err.message : 'Vorschau konnte nicht geladen werden';
                setError(message);
            } finally {
                if (!cancelled) {
                    setIsLoading(false);
                }
            }
        }

        loadPreview();

        return () => {
            cancelled = true;
            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
            }
        };
    }, [documentId]);

    // Cleanup bei unmount
    useEffect(() => {
        return () => {
            if (blobUrl) {
                URL.revokeObjectURL(blobUrl);
            }
        };
    }, [blobUrl]);

    return { blobUrl, isLoading, error, mimeType };
}

interface DocumentPreviewModalProps {
    documentId: string | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    documentName?: string;
    pageNumber?: number | null;
}

export function DocumentPreviewModal({
    documentId,
    open,
    onOpenChange,
    documentName,
}: DocumentPreviewModalProps) {
    const { blobUrl, isLoading, error, mimeType } = useAuthenticatedPreview(
        open ? documentId : null
    );
    const [scale, setScale] = useState(1.0);
    const scrollContainerRef = useRef<HTMLDivElement>(null);

    // Reset beim Oeffnen - bewusstes Pattern zum Zuruecksetzen des States
    useEffect(() => {
        if (open) {
            // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional reset on dialog open
            setScale(1.0);
            if (scrollContainerRef.current) {
                scrollContainerRef.current.scrollTop = 0;
            }
        }
    }, [open]);

    const isImage = mimeType?.startsWith('image/');
    const isPdf = mimeType === 'application/pdf';

    // Zoom nur für Bilder (PDF hat eigene Browser-Controls)
    const handleZoomIn = () => setScale((s) => Math.min(s + 0.25, 3));
    const handleZoomOut = () => setScale((s) => Math.max(s - 0.25, 0.25));
    const handleResetZoom = () => setScale(1.0);

    // Keyboard shortcuts nur für Bilder
    useEffect(() => {
        if (!open || isPdf) return;

        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === '+' || e.key === '=') {
                e.preventDefault();
                handleZoomIn();
            } else if (e.key === '-') {
                e.preventDefault();
                handleZoomOut();
            } else if (e.key === '0') {
                e.preventDefault();
                handleResetZoom();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [open, isPdf]);

    const displayTitle = documentName || 'Dokument';

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            {/* hideCloseButton via className to hide default X */}
            <DialogContent className="max-w-5xl w-[95vw] h-[90vh] flex flex-col p-0 gap-0 overflow-hidden [&>button]:hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                    <div className="flex items-center gap-3 min-w-0">
                        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary/10 text-primary shrink-0">
                            <FileText className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                            <DialogTitle className="text-base font-semibold truncate">
                                {displayTitle}
                            </DialogTitle>
                            {documentId && (
                                <p className="text-xs text-muted-foreground truncate">
                                    ID: {documentId.slice(0, 8)}...
                                </p>
                            )}
                        </div>
                    </div>

                    {/* Toolbar - Zoom nur bei Bildern */}
                    <div className="flex items-center gap-1">
                        {isImage && (
                            <>
                                <div className="flex items-center bg-muted/50 rounded-lg p-1">
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={handleZoomOut}
                                        disabled={scale <= 0.25}
                                        className="h-8 w-8 p-0"
                                        title="Verkleinern (-)"
                                    >
                                        <ZoomOut className="h-4 w-4" />
                                    </Button>
                                    <span className="text-sm font-medium min-w-[4rem] text-center tabular-nums">
                                        {Math.round(scale * 100)}%
                                    </span>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={handleZoomIn}
                                        disabled={scale >= 3}
                                        className="h-8 w-8 p-0"
                                        title="Vergrößern (+)"
                                    >
                                        <ZoomIn className="h-4 w-4" />
                                    </Button>
                                </div>

                                <Separator orientation="vertical" className="h-6 mx-1" />

                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={handleResetZoom}
                                    className="h-8 w-8 p-0"
                                    title="Zurücksetzen (0)"
                                >
                                    <RotateCcw className="h-4 w-4" />
                                </Button>

                                <Separator orientation="vertical" className="h-6 mx-1" />
                            </>
                        )}

                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onOpenChange(false)}
                            className="h-8 w-8 p-0 hover:bg-destructive/10 hover:text-destructive"
                            title="Schließen (Esc)"
                        >
                            <X className="h-4 w-4" />
                        </Button>
                    </div>
                </div>

                {/* Document Content Area */}
                <div
                    ref={scrollContainerRef}
                    className="flex-1 overflow-auto bg-muted/50"
                >
                    <div className="min-h-full p-4">
                        {/* Loading State */}
                        {isLoading && (
                            <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
                                <div className="relative">
                                    <div className="absolute inset-0 bg-primary/20 rounded-full blur-xl animate-pulse" />
                                    <Loader2 className="h-12 w-12 animate-spin text-primary relative" />
                                </div>
                                <p className="text-muted-foreground font-medium">
                                    Dokument wird geladen...
                                </p>
                            </div>
                        )}

                        {/* Error State */}
                        {error && (
                            <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
                                <div className="flex items-center justify-center w-16 h-16 rounded-full bg-destructive/10">
                                    <AlertTriangle className="h-8 w-8 text-destructive" />
                                </div>
                                <div className="text-center">
                                    <p className="font-semibold text-destructive">
                                        Fehler beim Laden
                                    </p>
                                    <p className="text-sm text-muted-foreground mt-1">{error}</p>
                                </div>
                                <Button
                                    variant="outline"
                                    onClick={() => onOpenChange(false)}
                                    className="mt-2"
                                >
                                    Schließen
                                </Button>
                            </div>
                        )}

                        {/* Image Preview */}
                        {!isLoading && !error && blobUrl && isImage && (
                            <div className="flex justify-center">
                                <div
                                    className={cn(
                                        'bg-background rounded-lg shadow-xl overflow-hidden',
                                        'ring-1 ring-border'
                                    )}
                                    style={{
                                        transform: `scale(${scale})`,
                                        transformOrigin: 'top center',
                                        transition: 'transform 0.2s ease-out',
                                    }}
                                >
                                    <img
                                        src={blobUrl}
                                        alt={documentName || 'Dokument'}
                                        className="max-w-none"
                                        style={{
                                            maxWidth: scale === 1 ? '100%' : 'none',
                                        }}
                                    />
                                </div>
                            </div>
                        )}

                        {/* PDF Preview - Browser PDF Viewer (hat eigene Zoom/Navigation) */}
                        {!isLoading && !error && blobUrl && isPdf && (
                            <div className="flex justify-center w-full h-full">
                                <iframe
                                    src={blobUrl}
                                    className={cn(
                                        'bg-background rounded-lg shadow-xl',
                                        'ring-1 ring-border',
                                        'w-full max-w-4xl'
                                    )}
                                    style={{
                                        height: `calc(90vh - 100px)`,
                                    }}
                                    title={documentName || 'PDF Preview'}
                                />
                            </div>
                        )}

                        {/* Unsupported Format */}
                        {!isLoading && !error && blobUrl && !isImage && !isPdf && (
                            <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
                                <div className="flex items-center justify-center w-16 h-16 rounded-full bg-muted">
                                    <FileText className="h-8 w-8 text-muted-foreground" />
                                </div>
                                <div className="text-center">
                                    <p className="font-semibold">
                                        Vorschau nicht verfügbar
                                    </p>
                                    <p className="text-sm text-muted-foreground mt-1">
                                        Dateityp: {mimeType || 'Unbekannt'}
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Footer - nur bei Bildern anzeigen */}
                {isImage && (
                    <div className="flex items-center justify-center gap-4 px-4 py-2 border-t bg-muted/30 text-xs text-muted-foreground">
                        <span>
                            <kbd className="px-1.5 py-0.5 bg-background rounded border text-[10px] font-mono">
                                +
                            </kbd>{' '}
                            /{' '}
                            <kbd className="px-1.5 py-0.5 bg-background rounded border text-[10px] font-mono">
                                -
                            </kbd>{' '}
                            Zoom
                        </span>
                        <span>
                            <kbd className="px-1.5 py-0.5 bg-background rounded border text-[10px] font-mono">
                                Esc
                            </kbd>{' '}
                            Schließen
                        </span>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
