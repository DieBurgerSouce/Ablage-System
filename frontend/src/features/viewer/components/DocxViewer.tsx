/**
 * DocxViewer - Word Document Viewer
 *
 * Rendert DOCX-Dateien im Browser mithilfe von Mammoth.js.
 * Konvertiert Word-Dokumente zu HTML fuer die Anzeige.
 * HTML wird mit DOMPurify sanitiert um XSS-Angriffe zu verhindern.
 */

import { useState, useEffect, useRef } from 'react';
import mammoth from 'mammoth';
import DOMPurify from 'dompurify';
import { Loader2, AlertTriangle, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { logger } from '@/lib/logger';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface DocxViewerProps {
    /** Blob URL or ArrayBuffer of the DOCX file */
    fileData: ArrayBuffer | Blob | string;
    /** Optional CSS class name */
    className?: string;
}

interface ConversionResult {
    html: string;
    messages: mammoth.Message[];
}

// ==================== Sanitization Config ====================

// Configure DOMPurify to allow safe HTML elements from Word docs
const PURIFY_CONFIG: DOMPurify.Config = {
    ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'br', 'hr',
        'ul', 'ol', 'li',
        'table', 'thead', 'tbody', 'tr', 'td', 'th',
        'strong', 'em', 'b', 'i', 'u', 's', 'sub', 'sup',
        'a', 'img',
        'blockquote', 'pre', 'code',
        'span', 'div',
    ],
    ALLOWED_ATTR: [
        'href', 'src', 'alt', 'title', 'class',
        'colspan', 'rowspan',
        'width', 'height',
    ],
    ALLOW_DATA_ATTR: false,
    ADD_TAGS: [],
    ADD_ATTR: [],
};

// ==================== Component ====================

export function DocxViewer({ fileData, className }: DocxViewerProps) {
    const [htmlContent, setHtmlContent] = useState<string | null>(null);
    const [messages, setMessages] = useState<mammoth.Message[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [scale, setScale] = useState(1.0);
    const contentRef = useRef<HTMLDivElement>(null);

    // Convert DOCX to HTML
    useEffect(() => {
        let cancelled = false;
        let abortController: AbortController | null = null;

        async function convertDocument() {
            setIsLoading(true);
            setError(null);

            try {
                let arrayBuffer: ArrayBuffer;

                if (fileData instanceof ArrayBuffer) {
                    arrayBuffer = fileData;
                } else if (fileData instanceof Blob) {
                    arrayBuffer = await fileData.arrayBuffer();
                } else if (typeof fileData === 'string') {
                    // Assume it's a blob URL - fetch with abort controller
                    abortController = new AbortController();
                    const response = await fetch(fileData, {
                        signal: abortController.signal,
                    });

                    // ENTERPRISE FIX: Validiere Response Status und Content-Type
                    if (!response.ok) {
                        throw new Error(
                            `Fetch fehlgeschlagen mit Status ${response.status}: ${response.statusText}`
                        );
                    }

                    const contentType = response.headers.get('content-type');
                    const validTypes = [
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'application/octet-stream',
                        'application/msword',
                    ];
                    if (contentType && !validTypes.some((t) => contentType.includes(t))) {
                        logger.warn(
                            `Unerwarteter Content-Type: ${contentType}. ` +
                            `Erwartet: DOCX oder application/octet-stream`
                        );
                    }

                    arrayBuffer = await response.arrayBuffer();
                } else {
                    throw new Error('Ungültiges Dateiformat');
                }

                if (cancelled) return;

                const result: ConversionResult = await mammoth.convertToHtml(
                    { arrayBuffer },
                    {
                        // Style mapping for better rendering
                        styleMap: [
                            "p[style-name='Heading 1'] => h1:fresh",
                            "p[style-name='Heading 2'] => h2:fresh",
                            "p[style-name='Heading 3'] => h3:fresh",
                            "p[style-name='Title'] => h1.document-title:fresh",
                            "p[style-name='Subtitle'] => p.document-subtitle:fresh",
                            "r[style-name='Strong'] => strong",
                            "r[style-name='Emphasis'] => em",
                        ],
                    }
                );

                if (cancelled) return;

                // ENTERPRISE FIX: Speichere RAW HTML - Sanitization erfolgt NUR EINMAL
                // im Render-Effect mit RETURN_DOM_FRAGMENT (sicherer und effizienter)
                // Vorher wurde doppelt sanitized: hier UND im Render-Effect
                setHtmlContent(result.value);
                setMessages(result.messages);
            } catch (err) {
                if (cancelled) return;
                // Ignore abort errors
                if (err instanceof Error && err.name === 'AbortError') {
                    return;
                }
                const message = err instanceof Error
                    ? err.message
                    : 'Dokument konnte nicht konvertiert werden';
                setError(message);
                logger.error('Fehler beim Konvertieren des Dokuments', err);
            } finally {
                if (!cancelled) {
                    setIsLoading(false);
                }
            }
        }

        convertDocument();

        return () => {
            cancelled = true;
            // Abort any in-flight fetch requests
            if (abortController) {
                abortController.abort();
            }
        };
    }, [fileData]);

    // Safely render sanitized HTML content using RETURN_DOM_FRAGMENT
    // Dies vermeidet redundante innerHTML Zuweisung und ist sicherer
    useEffect(() => {
        if (contentRef.current && htmlContent) {
            // SICHERHEIT: Verwende RETURN_DOM_FRAGMENT um innerHTML komplett zu vermeiden
            // DOMPurify gibt direkt ein DocumentFragment zurueck
            const fragment = DOMPurify.sanitize(htmlContent, {
                ...PURIFY_CONFIG,
                RETURN_DOM_FRAGMENT: true,
            });

            // Clear and append content
            contentRef.current.textContent = '';
            if (fragment instanceof DocumentFragment) {
                contentRef.current.appendChild(fragment.cloneNode(true));
            }
        }
    }, [htmlContent]);

    const handleZoomIn = () => setScale((s) => Math.min(s + 0.1, 2.0));
    const handleZoomOut = () => setScale((s) => Math.max(s - 0.1, 0.5));
    const handleResetZoom = () => setScale(1.0);

    // Show warnings if any
    const warnings = messages.filter((m) => m.type === 'warning');

    if (isLoading) {
        return (
            <div className={cn('h-full flex items-center justify-center bg-muted/30', className)}>
                <div className="flex flex-col items-center gap-3 text-muted-foreground">
                    <Loader2 className="h-8 w-8 animate-spin" />
                    <span>Konvertiere Dokument...</span>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className={cn('h-full flex items-center justify-center bg-muted/30', className)}>
                <div className="flex flex-col items-center gap-3 text-destructive">
                    <AlertTriangle className="h-8 w-8" />
                    <span>Dokument konnte nicht geladen werden</span>
                    <span className="text-xs text-muted-foreground">{error}</span>
                </div>
            </div>
        );
    }

    return (
        <div className={cn('h-full flex flex-col', className)}>
            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 py-2 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                <div className="flex items-center gap-1">
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleZoomOut}
                        disabled={scale <= 0.5}
                    >
                        <ZoomOut className="h-4 w-4" />
                    </Button>
                    <span className="text-sm text-muted-foreground w-16 text-center">
                        {Math.round(scale * 100)}%
                    </span>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={handleZoomIn}
                        disabled={scale >= 2.0}
                    >
                        <ZoomIn className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={handleResetZoom}>
                        <RotateCcw className="h-4 w-4" />
                    </Button>
                </div>
                {warnings.length > 0 && (
                    <span className="text-xs text-amber-500">
                        {warnings.length} Warnung(en) bei der Konvertierung
                    </span>
                )}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto bg-white dark:bg-zinc-900">
                <div
                    className="docx-content mx-auto p-8 max-w-4xl"
                    style={{
                        transform: `scale(${scale})`,
                        transformOrigin: 'top center',
                        minHeight: `${100 / scale}%`,
                    }}
                >
                    {/* Sanitized HTML content rendered here via useEffect */}
                    <div ref={contentRef} />
                </div>
            </div>

            {/* Embedded styles for DOCX content */}
            <style>{`
                .docx-content {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: inherit;
                }
                .docx-content h1 {
                    font-size: 2em;
                    font-weight: bold;
                    margin: 0.67em 0;
                    border-bottom: 1px solid hsl(var(--border));
                    padding-bottom: 0.3em;
                }
                .docx-content h2 {
                    font-size: 1.5em;
                    font-weight: bold;
                    margin: 0.83em 0;
                }
                .docx-content h3 {
                    font-size: 1.17em;
                    font-weight: bold;
                    margin: 1em 0;
                }
                .docx-content p {
                    margin: 1em 0;
                }
                .docx-content table {
                    border-collapse: collapse;
                    width: 100%;
                    margin: 1em 0;
                }
                .docx-content td, .docx-content th {
                    border: 1px solid hsl(var(--border));
                    padding: 0.5em;
                }
                .docx-content th {
                    background: hsl(var(--muted));
                    font-weight: bold;
                }
                .docx-content ul, .docx-content ol {
                    margin: 1em 0;
                    padding-left: 2em;
                }
                .docx-content li {
                    margin: 0.5em 0;
                }
                .docx-content img {
                    max-width: 100%;
                    height: auto;
                }
                .docx-content .document-title {
                    font-size: 2.5em;
                    text-align: center;
                    margin-bottom: 0.5em;
                }
                .docx-content .document-subtitle {
                    font-size: 1.2em;
                    text-align: center;
                    color: hsl(var(--muted-foreground));
                    margin-top: 0;
                }
            `}</style>
        </div>
    );
}

export default DocxViewer;
