/**
 * FilePreviewRouter - MIME Type Based Preview Router
 *
 * Routet Dateivorschauen basierend auf dem MIME-Typ zur passenden
 * Viewer-Komponente (PDF, Bild, DOCX, XLSX, Email).
 */

import { lazy, Suspense } from 'react';
import { Loader2, FileQuestion } from 'lucide-react';
import { cn } from '@/lib/utils';

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
            // PDF is handled by SplitDocumentViewer (react-pdf)
            // This router is for the other types
            return (
                <UnsupportedTypeFallback
                    mimeType={mimeType}
                    filename={filename}
                    className={className}
                />
            );

        case 'image':
            // Images are handled by ImageViewer in SplitDocumentViewer
            return (
                <UnsupportedTypeFallback
                    mimeType={mimeType}
                    filename={filename}
                    className={className}
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
            // For text files, we could add a simple text viewer
            // For now, treat as unsupported
            return (
                <UnsupportedTypeFallback
                    mimeType={mimeType}
                    filename={filename}
                    className={className}
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
