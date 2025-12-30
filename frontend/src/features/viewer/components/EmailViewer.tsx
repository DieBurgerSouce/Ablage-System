/**
 * EmailViewer - Email (.eml) Viewer
 *
 * Parst und zeigt E-Mails im RFC 822 Format (.eml Dateien) an.
 * Zeigt Header, Body (Text/HTML) und Anhaenge.
 */

import { useState, useEffect, useRef } from 'react';
import DOMPurify from 'dompurify';
import {
    Loader2,
    AlertTriangle,
    Mail,
    User,
    Users,
    Calendar,
    Paperclip,
    FileText,
    ChevronDown,
    ChevronUp,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface EmailViewerProps {
    /** Raw EML file data */
    fileData: ArrayBuffer | Blob | string;
    /** Optional CSS class name */
    className?: string;
}

interface EmailHeader {
    from: string;
    to: string[];
    cc: string[];
    bcc: string[];
    subject: string;
    date: string;
    messageId?: string;
    replyTo?: string;
}

interface EmailAttachment {
    filename: string;
    contentType: string;
    size: number;
    content?: ArrayBuffer;
}

interface ParsedEmail {
    headers: EmailHeader;
    textBody?: string;
    htmlBody?: string;
    attachments: EmailAttachment[];
    rawHeaders: Record<string, string>;
}

// ==================== Email Parser ====================

/**
 * Parse RFC 822 email format
 * This is a simplified parser for basic .eml files
 */
function parseEmail(rawEmail: string): ParsedEmail {
    const lines = rawEmail.replace(/\r\n/g, '\n').split('\n');

    // Find header/body boundary (empty line)
    let headerEndIndex = 0;
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].trim() === '') {
            headerEndIndex = i;
            break;
        }
    }

    // Parse headers
    const rawHeaders: Record<string, string> = {};
    let currentHeader = '';
    let currentValue = '';

    for (let i = 0; i < headerEndIndex; i++) {
        const line = lines[i];
        if (line.startsWith(' ') || line.startsWith('\t')) {
            // Continuation of previous header
            currentValue += ' ' + line.trim();
        } else {
            // Save previous header
            if (currentHeader) {
                rawHeaders[currentHeader.toLowerCase()] = currentValue;
            }
            // Start new header
            const colonIndex = line.indexOf(':');
            if (colonIndex > 0) {
                currentHeader = line.substring(0, colonIndex).trim();
                currentValue = line.substring(colonIndex + 1).trim();
            }
        }
    }
    // Save last header
    if (currentHeader) {
        rawHeaders[currentHeader.toLowerCase()] = currentValue;
    }

    // Extract structured headers
    const headers: EmailHeader = {
        from: rawHeaders['from'] || '',
        to: parseAddressList(rawHeaders['to'] || ''),
        cc: parseAddressList(rawHeaders['cc'] || ''),
        bcc: parseAddressList(rawHeaders['bcc'] || ''),
        subject: decodeEncodedWords(rawHeaders['subject'] || ''),
        date: rawHeaders['date'] || '',
        messageId: rawHeaders['message-id'],
        replyTo: rawHeaders['reply-to'],
    };

    // Parse body
    const bodyLines = lines.slice(headerEndIndex + 1);
    const bodyText = bodyLines.join('\n');

    // Check content type
    const contentType = rawHeaders['content-type'] || 'text/plain';
    const isMultipart = contentType.toLowerCase().includes('multipart');

    let textBody: string | undefined;
    let htmlBody: string | undefined;
    const attachments: EmailAttachment[] = [];

    if (isMultipart) {
        // Parse multipart message
        const boundaryMatch = contentType.match(/boundary="?([^";\s]+)"?/i);
        if (boundaryMatch) {
            const boundary = boundaryMatch[1];
            const parts = parseMultipart(bodyText, boundary);

            for (const part of parts) {
                const partContentType = (part.headers['content-type'] || 'text/plain').toLowerCase();

                if (partContentType.includes('text/plain') && !textBody) {
                    textBody = part.body;
                } else if (partContentType.includes('text/html') && !htmlBody) {
                    htmlBody = part.body;
                } else if (part.headers['content-disposition']?.includes('attachment')) {
                    const filenameMatch = part.headers['content-disposition'].match(/filename="?([^";\n]+)"?/i);
                    attachments.push({
                        filename: filenameMatch?.[1] || 'Anhang',
                        contentType: partContentType.split(';')[0],
                        size: part.body.length,
                    });
                }
            }
        }
    } else {
        // Simple message
        if (contentType.toLowerCase().includes('text/html')) {
            htmlBody = bodyText;
        } else {
            textBody = bodyText;
        }
    }

    return {
        headers,
        textBody,
        htmlBody,
        attachments,
        rawHeaders,
    };
}

/**
 * Parse multipart message into parts
 */
function parseMultipart(body: string, boundary: string): Array<{ headers: Record<string, string>; body: string }> {
    const parts: Array<{ headers: Record<string, string>; body: string }> = [];
    const delimiter = '--' + boundary;
    const sections = body.split(delimiter);

    for (let i = 1; i < sections.length; i++) {
        const section = sections[i];
        if (section.startsWith('--')) continue; // End marker

        const lines = section.split('\n');
        const partHeaders: Record<string, string> = {};
        let bodyStart = 0;

        // Parse part headers
        for (let j = 0; j < lines.length; j++) {
            const line = lines[j].trim();
            if (line === '') {
                bodyStart = j + 1;
                break;
            }
            const colonIdx = line.indexOf(':');
            if (colonIdx > 0) {
                partHeaders[line.substring(0, colonIdx).toLowerCase()] = line.substring(colonIdx + 1).trim();
            }
        }

        parts.push({
            headers: partHeaders,
            body: lines.slice(bodyStart).join('\n').trim(),
        });
    }

    return parts;
}

/**
 * Parse comma-separated address list
 */
function parseAddressList(addressString: string): string[] {
    if (!addressString) return [];
    return addressString
        .split(',')
        .map((addr) => decodeEncodedWords(addr.trim()))
        .filter(Boolean);
}

/**
 * Decode RFC 2047 encoded words (=?charset?encoding?text?=)
 */
function decodeEncodedWords(text: string): string {
    return text.replace(/=\?([^?]+)\?([BQ])\?([^?]+)\?=/gi, (match, charset, encoding, encoded) => {
        try {
            if (encoding.toUpperCase() === 'B') {
                // Base64
                return atob(encoded);
            } else if (encoding.toUpperCase() === 'Q') {
                // Quoted-Printable
                return encoded
                    .replace(/_/g, ' ')
                    .replace(/=([0-9A-F]{2})/gi, (m: string, hex: string) =>
                        String.fromCharCode(parseInt(hex, 16))
                    );
            }
        } catch {
            // Return original if decoding fails
        }
        return match;
    });
}

/**
 * Format email date
 */
function formatEmailDate(dateString: string): string {
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return dateString;
        return date.toLocaleString('de-DE', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch {
        return dateString;
    }
}

// ==================== DOMPurify Config ====================

/**
 * SECURITY: Strikte DOMPurify-Konfiguration fuer E-Mail-HTML
 *
 * WICHTIG: Keine 'style' Attribute erlaubt (CSS-Injection-Risiko)
 * WICHTIG: Keine 'style' Tags erlaubt (CSS-Angriffsvektoren)
 * WICHTIG: data: URIs in src blockiert
 *
 * E-Mails sind nicht vertrauenswuerdige Eingaben - minimale Erlaubnisse!
 */
const PURIFY_CONFIG: DOMPurify.Config = {
    ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'br', 'hr', 'div', 'span',
        'ul', 'ol', 'li',
        'table', 'thead', 'tbody', 'tr', 'td', 'th',
        'strong', 'em', 'b', 'i', 'u', 's',
        'a', 'img',
        'blockquote', 'pre', 'code',
    ],
    // SECURITY: 'style' absichtlich NICHT erlaubt - CSS-Injection-Risiko!
    ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class'],
    ALLOW_DATA_ATTR: false,
    // Explizit gefaehrliche Tags verbieten
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'input', 'style', 'link', 'meta'],
    // Gefaehrliche Attribute explizit verbieten
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick', 'onmouseover'],
    RETURN_DOM: true,
    RETURN_DOM_FRAGMENT: true,
};

// ==================== DOMPurify Hooks (Module-Level, Once Only) ====================

/**
 * WICHTIG: DOMPurify Hooks muessen EINMAL registriert werden, nicht bei jedem Mount!
 * Ohne Guard wuerden sich Hooks bei jedem Component Mount akkumulieren.
 */
let domPurifyHooksRegistered = false;

function registerDOMPurifySecurityHooks(): void {
    if (domPurifyHooksRegistered) return;
    domPurifyHooksRegistered = true;

    // Zusaetzliche Hooks fuer erweiterte Sicherheit
    DOMPurify.addHook('uponSanitizeAttribute', (node, data) => {
        // Blockiere data: URIs in src (potenzielle Script-Injection)
        if (data.attrName === 'src' && data.attrValue.startsWith('data:')) {
            data.attrValue = '';
        }
        // Blockiere javascript: URIs in href
        if (data.attrName === 'href' && data.attrValue.toLowerCase().startsWith('javascript:')) {
            data.attrValue = '#';
        }
    });
}

// Register hooks immediately at module load time (happens once per app lifecycle)
registerDOMPurifySecurityHooks();

// ==================== Component ====================

export function EmailViewer({ fileData, className }: EmailViewerProps) {
    const [email, setEmail] = useState<ParsedEmail | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showHtml, setShowHtml] = useState(true);
    const [showRawHeaders, setShowRawHeaders] = useState(false);
    const htmlContentRef = useRef<HTMLDivElement>(null);

    // Parse email file
    useEffect(() => {
        let cancelled = false;

        async function loadEmail() {
            setIsLoading(true);
            setError(null);

            try {
                let rawText: string;

                if (typeof fileData === 'string') {
                    // URL - fetch it
                    const response = await fetch(fileData);

                    // ENTERPRISE FIX: Validiere Response Status
                    // Konsistent mit DocxViewer.tsx (Line 88)
                    if (!response.ok) {
                        throw new Error(
                            `Fetch fehlgeschlagen mit Status ${response.status}: ${response.statusText}`
                        );
                    }

                    rawText = await response.text();
                } else if (fileData instanceof Blob) {
                    rawText = await fileData.text();
                } else if (fileData instanceof ArrayBuffer) {
                    const decoder = new TextDecoder('utf-8');
                    rawText = decoder.decode(fileData);
                } else {
                    throw new Error('Ungueltiges Dateiformat');
                }

                if (cancelled) return;

                const parsed = parseEmail(rawText);
                setEmail(parsed);
            } catch (err) {
                if (cancelled) return;
                const message = err instanceof Error
                    ? err.message
                    : 'E-Mail konnte nicht geladen werden';
                setError(message);
                console.error('[EmailViewer] Parse error:', err);
            } finally {
                if (!cancelled) {
                    setIsLoading(false);
                }
            }
        }

        loadEmail();

        return () => {
            cancelled = true;
        };
    }, [fileData]);

    // Safely render sanitized HTML content using DOMPurify
    useEffect(() => {
        if (htmlContentRef.current && email?.htmlBody && showHtml) {
            // Clear existing content
            htmlContentRef.current.textContent = '';

            // Use DOMPurify to sanitize and get a DocumentFragment directly
            const cleanFragment = DOMPurify.sanitize(email.htmlBody, PURIFY_CONFIG);

            // Append the sanitized fragment
            if (cleanFragment instanceof DocumentFragment) {
                htmlContentRef.current.appendChild(cleanFragment.cloneNode(true));
            }
        }
    }, [email?.htmlBody, showHtml]);

    if (isLoading) {
        return (
            <div className={cn('h-full flex items-center justify-center bg-muted/30', className)}>
                <div className="flex flex-col items-center gap-3 text-muted-foreground">
                    <Loader2 className="h-8 w-8 animate-spin" />
                    <span>Lade E-Mail...</span>
                </div>
            </div>
        );
    }

    if (error || !email) {
        return (
            <div className={cn('h-full flex items-center justify-center bg-muted/30', className)}>
                <div className="flex flex-col items-center gap-3 text-destructive">
                    <AlertTriangle className="h-8 w-8" />
                    <span>E-Mail konnte nicht geladen werden</span>
                    <span className="text-xs text-muted-foreground">{error}</span>
                </div>
            </div>
        );
    }

    const hasHtmlBody = Boolean(email.htmlBody);
    const hasTextBody = Boolean(email.textBody);

    return (
        <div className={cn('h-full flex flex-col overflow-hidden', className)}>
            {/* Email Header */}
            <div className="p-4 border-b bg-background space-y-3">
                {/* Subject */}
                <div className="flex items-start gap-3">
                    <Mail className="h-5 w-5 text-primary mt-0.5 flex-shrink-0" />
                    <h2 className="text-lg font-semibold leading-tight">
                        {email.headers.subject || '(Kein Betreff)'}
                    </h2>
                </div>

                {/* From */}
                <div className="flex items-center gap-3 text-sm">
                    <User className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <span className="text-muted-foreground">Von:</span>
                    <span className="font-medium">{email.headers.from || 'Unbekannt'}</span>
                </div>

                {/* To */}
                {email.headers.to.length > 0 && (
                    <div className="flex items-start gap-3 text-sm">
                        <Users className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                        <span className="text-muted-foreground">An:</span>
                        <span>{email.headers.to.join(', ')}</span>
                    </div>
                )}

                {/* CC */}
                {email.headers.cc.length > 0 && (
                    <div className="flex items-start gap-3 text-sm">
                        <Users className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                        <span className="text-muted-foreground">CC:</span>
                        <span>{email.headers.cc.join(', ')}</span>
                    </div>
                )}

                {/* Date */}
                {email.headers.date && (
                    <div className="flex items-center gap-3 text-sm">
                        <Calendar className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                        <span className="text-muted-foreground">Datum:</span>
                        <span>{formatEmailDate(email.headers.date)}</span>
                    </div>
                )}

                {/* Attachments */}
                {email.attachments.length > 0 && (
                    <div className="flex items-start gap-3 text-sm">
                        <Paperclip className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                        <span className="text-muted-foreground">Anhaenge:</span>
                        <div className="flex flex-wrap gap-2">
                            {email.attachments.map((att, idx) => (
                                <Badge key={idx} variant="secondary" className="gap-1">
                                    <FileText className="h-3 w-3" />
                                    {att.filename}
                                </Badge>
                            ))}
                        </div>
                    </div>
                )}

                {/* View toggle */}
                {hasHtmlBody && hasTextBody && (
                    <div className="flex items-center gap-2 pt-2">
                        <Button
                            variant={showHtml ? 'default' : 'outline'}
                            size="sm"
                            onClick={() => setShowHtml(true)}
                        >
                            HTML
                        </Button>
                        <Button
                            variant={!showHtml ? 'default' : 'outline'}
                            size="sm"
                            onClick={() => setShowHtml(false)}
                        >
                            Text
                        </Button>
                    </div>
                )}
            </div>

            <Separator />

            {/* Email Body */}
            <div className="flex-1 overflow-auto p-4 bg-white dark:bg-zinc-900">
                {showHtml && hasHtmlBody ? (
                    <div
                        ref={htmlContentRef}
                        className="email-html-content prose prose-sm dark:prose-invert max-w-none"
                    />
                ) : hasTextBody ? (
                    <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
                        {email.textBody}
                    </pre>
                ) : (
                    <p className="text-muted-foreground italic">
                        Kein Inhalt verfuegbar
                    </p>
                )}
            </div>

            {/* Raw Headers (Collapsible) */}
            <Collapsible open={showRawHeaders} onOpenChange={setShowRawHeaders}>
                <CollapsibleTrigger asChild>
                    <Button
                        variant="ghost"
                        size="sm"
                        className="w-full justify-between rounded-none border-t"
                    >
                        <span className="text-xs">Rohe Header anzeigen</span>
                        {showRawHeaders ? (
                            <ChevronUp className="h-4 w-4" />
                        ) : (
                            <ChevronDown className="h-4 w-4" />
                        )}
                    </Button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                    <div className="max-h-48 overflow-auto p-4 bg-muted/30 text-xs font-mono">
                        {Object.entries(email.rawHeaders).map(([key, value]) => (
                            <div key={key} className="mb-1">
                                <span className="text-primary font-semibold">{key}:</span>{' '}
                                <span className="text-muted-foreground">{value}</span>
                            </div>
                        ))}
                    </div>
                </CollapsibleContent>
            </Collapsible>

            {/* Embedded styles for HTML email content */}
            <style>{`
                .email-html-content {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .email-html-content img {
                    max-width: 100%;
                    height: auto;
                }
                .email-html-content a {
                    color: hsl(var(--primary));
                }
                .email-html-content table {
                    border-collapse: collapse;
                }
                .email-html-content td, .email-html-content th {
                    padding: 4px 8px;
                }
            `}</style>
        </div>
    );
}

export default EmailViewer;

// ==================== HMR Cleanup (Development Only) ====================

/**
 * KRITISCH: Bei Hot Module Replacement (HMR) in Vite/Webpack muss der
 * domPurifyHooksRegistered Flag zurueckgesetzt werden, sonst akkumulieren
 * sich Hooks bei jedem Hot Reload.
 */
if (import.meta.hot) {
    import.meta.hot.dispose(() => {
        domPurifyHooksRegistered = false;
        // Entferne alle DOMPurify Hooks bei HMR
        DOMPurify.removeAllHooks();
    });
}

// ==================== Test Utilities (Test Environment Only) ====================

/**
 * ENTERPRISE FIX: Reset-Funktion fuer Test-Isolation
 *
 * Problem: Der Module-Level Boolean verhindert Hook-Neuregistrierung zwischen Tests.
 * In einer Test-Suite, wo Tests isoliert sein sollten, kann dies zu unerwarteten
 * Seiteneffekten fuehren wenn Tests in unterschiedlicher Reihenfolge laufen.
 *
 * Diese Funktion ermoeglicht es Tests, den DOMPurify-State zurueckzusetzen.
 * Sie ist NUR in Test-Umgebung verfuegbar und sollte NICHT in Produktion verwendet werden.
 */
export function __resetDOMPurifyHooks(): void {
    if (process.env.NODE_ENV === 'test' || import.meta.env?.MODE === 'test') {
        domPurifyHooksRegistered = false;
        DOMPurify.removeAllHooks();
    } else {
        console.warn(
            '[EmailViewer] __resetDOMPurifyHooks sollte nur in Tests verwendet werden'
        );
    }
}
