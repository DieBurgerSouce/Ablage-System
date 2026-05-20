/**
 * FilePreviewRouter - MIME Type Based Preview Router
 *
 * Routet Dateivorschauen basierend auf dem MIME-Typ zur passenden
 * Viewer-Komponente (PDF, Bild, DOCX, XLSX, Email, Text).
 */

import { lazy, Suspense, useState, useMemo, useEffect } from 'react';
import { Loader2, FileQuestion, AlertTriangle } from 'lucide-react';
import { Document, Page, pdfjs } from 'react-pdf';
import { cn } from '@/lib/utils';

// PDF.js Worker setup
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// ==================== Lazy Loaded Viewers ====================

// Lazy load heavy viewer components
const DocxViewer = lazy(() => import('./DocxViewer'));
const XlsxViewer = lazy(() => import('./XlsxViewer'));
const EmailViewer = lazy(() => import('./EmailViewer'));

// ==================== Types ====================

export type SupportedMimeType =
    | 'application/pdf'
    | 'image/png'
    | 'image/jpeg'
    | 'image/gif'
    | 'image/webp'
    | 'image/tiff'
    | 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    | 'application/msword'
    | 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    | 'application/vnd.ms-excel'
    | 'message/rfc822'
    | 'text/plain';

interface FilePreviewRouterProps {
    /** File data as ArrayBuffer, Blob, or URL string */
    fileData: ArrayBuffer | Blob | string;
    /** MIME type of the file */
    mimeType: string;
    /** Original filename (for display and type detection fallback) */
    filename?: string;
    /** Optional CSS class name */
    className?: string;
    /** Callback for when the preview fails */
    onError?: (error: Error) => void;
}

// ==================== MIME Type Helpers ====================

/**
 * Kategorisiert einen MIME-Typ
 */
type FileCategory = 'pdf' | 'image' | 'docx' | 'xlsx' | 'email' | 'text' | 'unknown';

function categorizeFileType(mimeType: string, filename?: string): FileCategory {
    const mime = mimeType.toLowerCase();

    // PDF
    if (mime === 'application/pdf') {
        return 'pdf';
    }

    // Images
    if (mime.startsWith('image/')) {
        return 'image';
    }

    // Word Documents
    if (
        mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
        mime === 'application/msword'
    ) {
        return 'docx';
    }

    // Excel Spreadsheets
    if (
        mime === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
        mime === 'application/vnd.ms-excel'
    ) {
        return 'xlsx';
    }

    // Email
    if (mime === 'message/rfc822') {
        return 'email';
    }

    // Plain text
    if (mime === 'text/plain') {
        return 'text';
    }

    // Fallback to filename extension
    if (filename) {
        const ext = filename.split('.').pop()?.toLowerCase();
        switch (ext) {
            case 'pdf':
                return 'pdf';
            case 'png':
            case 'jpg':
            case 'jpeg':
            case 'gif':
            case 'webp':
            case 'tiff':
            case 'tif':
                return 'image';
            case 'docx':
            case 'doc':
                return 'docx';
            case 'xlsx':
            case 'xls':
                return 'xlsx';
            case 'eml':
                return 'email';
            case 'txt':
                return 'text';
        }
    }

    return 'unknown';
}

/**
 * Get human-readable file type name
 */
function getFileTypeName(category: FileCategory): string {
    const names: Record<FileCategory, string> = {
        pdf: 'PDF-Dokument',
        image: 'Bild',
        docx: 'Word-Dokument',
        xlsx: 'Excel-Tabelle',
        email: 'E-Mail',
        text: 'Textdatei',
        unknown: 'Unbekannter Dateityp',
    };
    return names[category];
}

// ==================== Loading Fallback ====================

function LoadingFallback({ className }: { className?: string }) {
    return (
        <div className={cn('h-full flex items-center justify-center bg-muted/30', className)}>
            <div className="flex flex-col items-center gap-3 text-muted-foreground">
                <Loader2 className="h-8 w-8 animate-spin" />
                <span>Lade Vorschau...</span>
            </div>
        </div>
    );
}

// ==================== Simple PDF Viewer ====================

interface SimplePdfViewerProps {
    fileData: ArrayBuffer | Blob | string;
    className?: string;
    onError?: (error: Error) => void;
}

function SimplePdfViewer({ fileData, className, onError }: SimplePdfViewerProps) {
    const [numPages, setNumPages] = useState<number | null>(null);
    const [currentPage, setCurrentPage] = useState(1);
    const [error, setError] = useState<string | null>(null);

    // Convert fileData to a format react-pdf can use
    const pdfSource = useMemo(() => {
        if (typeof fileData === 'string') {
            return fileData; // URL or data URL
        }
        if (fileData instanceof Blob) {
            return URL.createObjectURL(fileData);
        }
        // ArrayBuffer - convert to Blob then URL
        return URL.createObjectURL(new Blob([fileData], { type: 'application/pdf' }));
    }, [fileData]);

    // Cleanup blob URL
    useEffect(() => {
        return () => {
            if (typeof fileData !== 'string' && pdfSource.startsWith('blob:')) {
                URL.revokeObjectURL(pdfSource);
            }
        };
    }, [pdfSource, fileData]);

    return (
        <div className={cn('h-full overflow-auto bg-muted/30 flex flex-col', className)}>
            {error ? (
                <div className="flex-1 flex items-center justify-center">
                    <div className="flex flex-col items-center gap-3 text-destructive">
                        <AlertTriangle className="h-8 w-8" />
                        <span>PDF konnte nicht geladen werden</span>
                        <span className="text-xs text-muted-foreground">{error}</span>
                    </div>
                </div>
            ) : (
                <>
                    {numPages && numPages > 1 && (
                        <div className="sticky top-0 bg-background/95 backdrop-blur px-4 py-2 border-b flex items-center justify-center gap-4 z-10">
                            <button
                                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                disabled={currentPage <= 1}
                                className="px-3 py-1 text-sm rounded border hover:bg-muted disabled:opacity-50"
                            >
                                Zurück
                            </button>
                            <span className="text-sm">
                                Seite {currentPage} von {numPages}
                            </span>
                            <button
                                onClick={() => setCurrentPage(p => Math.min(numPages, p + 1))}
                                disabled={currentPage >= numPages}
                                className="px-3 py-1 text-sm rounded border hover:bg-muted disabled:opacity-50"
                            >
                                Weiter
                            </button>
                        </div>
                    )}
                    <div className="flex-1 flex justify-center p-4">
                        <Document
                            file={pdfSource}
                            onLoadSuccess={({ numPages }) => setNumPages(numPages)}
                            onLoadError={(err) => {
                                const message = err instanceof Error ? err.message : 'Unbekannter Fehler';
                                setError(message);
                                onError?.(err instanceof Error ? err : new Error(message));
                            }}
                            className="shadow-lg"
                            loading={<LoadingFallback />}
                        >
                            <Page
                                pageNumber={currentPage}
                                renderTextLayer={true}
                                renderAnnotationLayer={true}
                            />
                        </Document>
                    </div>
                </>
            )}
        </div>
    );
}

// ==================== Simple Image Viewer ====================

interface SimpleImageViewerProps {
    fileData: ArrayBuffer | Blob | string;
    className?: string;
    onError?: (error: Error) => void;
}

function SimpleImageViewer({ fileData, className, onError }: SimpleImageViewerProps) {
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    // Convert fileData to a displayable URL
    const imageUrl = useMemo(() => {
        if (typeof fileData === 'string') {
            return fileData;
        }
        if (fileData instanceof Blob) {
            return URL.createObjectURL(fileData);
        }
        // ArrayBuffer
        return URL.createObjectURL(new Blob([fileData]));
    }, [fileData]);

    // Cleanup blob URL
    useEffect(() => {
        return () => {
            if (typeof fileData !== 'string' && imageUrl.startsWith('blob:')) {
                URL.revokeObjectURL(imageUrl);
            }
        };
    }, [imageUrl, fileData]);

    // Error state takes precedence
    if (error) {
        return (
            <div className={cn('h-full overflow-auto bg-muted/30 flex items-center justify-center p-4', className)}>
                <div className="flex flex-col items-center gap-3 text-destructive">
                    <AlertTriangle className="h-8 w-8" />
                    <span>Bild konnte nicht geladen werden</span>
                </div>
            </div>
        );
    }

    return (
        <div className={cn('h-full overflow-auto bg-muted/30 flex items-center justify-center p-4 relative', className)}>
            {/* Loading indicator shown while image loads */}
            {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-muted/30">
                    <LoadingFallback />
                </div>
            )}
            <img
                src={imageUrl}
                alt="Vorschau"
                className={cn(
                    'max-w-full max-h-full object-contain shadow-lg transition-opacity duration-200',
                    isLoading ? 'opacity-0' : 'opacity-100'
                )}
                onLoad={() => setIsLoading(false)}
                onError={() => {
                    setIsLoading(false);
                    setError('Bild konnte nicht geladen werden');
                    onError?.(new Error('Failed to load image'));
                }}
            />
        </div>
    );
}

// ==================== Simple Text Viewer ====================

interface SimpleTextViewerProps {
    fileData: ArrayBuffer | Blob | string;
    className?: string;
    onError?: (error: Error) => void;
}

function SimpleTextViewer({ fileData, className, onError }: SimpleTextViewerProps) {
    const [text, setText] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;

        async function loadText() {
            try {
                let content: string;

                if (typeof fileData === 'string') {
                    // Could be a URL or text content
                    if (fileData.startsWith('blob:') || fileData.startsWith('http')) {
                        const response = await fetch(fileData);
                        content = await response.text();
                    } else {
                        content = fileData;
                    }
                } else if (fileData instanceof Blob) {
                    content = await fileData.text();
                } else {
                    // ArrayBuffer
                    const decoder = new TextDecoder('utf-8');
                    content = decoder.decode(fileData);
                }

                if (!cancelled) {
                    setText(content);
                    setIsLoading(false);
                }
            } catch (err) {
                if (!cancelled) {
                    const message = err instanceof Error ? err.message : 'Fehler beim Laden';
                    setError(message);
                    setIsLoading(false);
                    onError?.(err instanceof Error ? err : new Error(message));
                }
            }
        }

        loadText();

        return () => {
            cancelled = true;
        };
    }, [fileData, onError]);

    return (
        <div className={cn('h-full overflow-auto bg-muted/30', className)}>
            {isLoading ? (
                <LoadingFallback />
            ) : error ? (
                <div className="flex items-center justify-center h-full">
                    <div className="flex flex-col items-center gap-3 text-destructive">
                        <AlertTriangle className="h-8 w-8" />
                        <span>Text konnte nicht geladen werden</span>
                    </div>
                </div>
            ) : (
                <pre className="p-4 text-sm font-mono whitespace-pre-wrap break-words">
                    {text}
                </pre>
            )}
        </div>
    );
}

// ==================== Unsupported Type Fallback ====================

interface UnsupportedTypeFallbackProps {
    mimeType: string;
    filename?: string;
    className?: string;
}

function UnsupportedTypeFallback({ mimeType, filename, className }: UnsupportedTypeFallbackProps) {
    return (
        <div className={cn('h-full flex items-center justify-center bg-muted/30', className)}>
            <div className="flex flex-col items-center gap-4 text-muted-foreground max-w-md text-center p-8">
                <FileQuestion className="h-16 w-16" />
                <div className="space-y-2">
                    <h3 className="text-lg font-medium text-foreground">
                        Vorschau nicht verfügbar
                    </h3>
                    <p className="text-sm">
                        Für diesen Dateityp ist keine Vorschau verfügbar.
                    </p>
                </div>
                <div className="text-xs space-y-1">
                    {filename && <p>Datei: {filename}</p>}
                    <p>MIME-Typ: {mimeType}</p>
                </div>
            </div>
        </div>
    );
}

// ==================== Component ====================

export function FilePreviewRouter({
    fileData,
    mimeType,
    filename,
    className,
    onError,
}: FilePreviewRouterProps) {
    const category = categorizeFileType(mimeType, filename);

    // Route to appropriate viewer
    switch (category) {
        case 'pdf':
            return (
                <SimplePdfViewer
                    fileData={fileData}
                    className={className}
                    onError={onError}
                />
            );

        case 'image':
            return (
                <SimpleImageViewer
                    fileData={fileData}
                    className={className}
                    onError={onError}
                />
            );

        case 'docx':
            return (
                <Suspense fallback={<LoadingFallback className={className} />}>
                    <DocxViewer fileData={fileData} className={className} />
                </Suspense>
            );

        case 'xlsx':
            return (
                <Suspense fallback={<LoadingFallback className={className} />}>
                    <XlsxViewer fileData={fileData} className={className} />
                </Suspense>
            );

        case 'email':
            return (
                <Suspense fallback={<LoadingFallback className={className} />}>
                    <EmailViewer fileData={fileData} className={className} />
                </Suspense>
            );

        case 'text':
            return (
                <SimpleTextViewer
                    fileData={fileData}
                    className={className}
                    onError={onError}
                />
            );

        case 'unknown':
        default:
            return (
                <UnsupportedTypeFallback
                    mimeType={mimeType}
                    filename={filename}
                    className={className}
                />
            );
    }
}

// ==================== Exports ====================

export { categorizeFileType, getFileTypeName };
export type { FileCategory };
export default FilePreviewRouter;
