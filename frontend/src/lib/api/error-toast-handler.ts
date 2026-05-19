/**
 * Globaler Error-Toast Handler für API-Fehler.
 *
 * K3 KRITISCH: Error Toasts für API-Fehler
 *
 * Zeigt automatisch Toast-Benachrichtigungen für:
 * - Netzwerkfehler (keine Verbindung)
 * - 500 Server-Fehler
 * - 429 Rate Limit
 * - 503 Service Unavailable
 */

import { AxiosError } from 'axios';
import { logger } from '@/lib/logger';
import { toast } from '@/components/ui/use-toast';
import { toast as sonnerToast } from 'sonner';
import { apiClient } from '@/lib/api/client';

/**
 * Error-Nachricht-Mapping (Deutsch)
 */
const ERROR_MESSAGES: Record<string, { title: string; description: string }> = {
    // Network Errors
    NETWORK_ERROR: {
        title: 'Keine Verbindung',
        description: 'Keine Verbindung zum Server. Bitte prüfen Sie Ihre Internetverbindung.',
    },
    TIMEOUT: {
        title: 'Zeitüberschreitung',
        description: 'Die Anfrage hat zu lange gedauert. Bitte versuchen Sie es erneut.',
    },

    // HTTP Status Errors
    400: {
        title: 'Ungültige Anfrage',
        description: 'Die Anfrage war fehlerhaft. Bitte überprüfen Sie Ihre Eingaben.',
    },
    401: {
        title: 'Nicht autorisiert',
        description: 'Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.',
    },
    403: {
        title: 'Zugriff verweigert',
        description: 'Sie haben keine Berechtigung für diese Aktion.',
    },
    404: {
        title: 'Nicht gefunden',
        description: 'Die angeforderte Ressource wurde nicht gefunden.',
    },
    409: {
        title: 'Konflikt',
        description: 'Die Anfrage konnte wegen eines Konflikts nicht ausgeführt werden.',
    },
    422: {
        title: 'Validierungsfehler',
        description: 'Die eingegebenen Daten sind ungültig.',
    },
    429: {
        title: 'Zu viele Anfragen',
        description: 'Sie haben zu viele Anfragen gesendet. Bitte warten Sie einen Moment.',
        // Fix 7: Retry-After wird dynamisch hinzugefügt in showApiErrorToast()
    },
    500: {
        title: 'Server-Fehler',
        description: 'Ein interner Server-Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.',
    },
    502: {
        title: 'Server nicht erreichbar',
        description: 'Der Server ist vorübergehend nicht erreichbar.',
    },
    503: {
        title: 'Dienst nicht verfügbar',
        description: 'Der Dienst ist vorübergehend nicht verfügbar. Bitte versuchen Sie es später erneut.',
    },
    504: {
        title: 'Gateway-Zeitüberschreitung',
        description: 'Der Server hat nicht rechtzeitig geantwortet.',
    },
};

/**
 * Statuscodes, die keinen Toast anzeigen sollen
 * (werden bereits anderweitig behandelt, z.B. durch Session-Expired-Modal)
 */
const SILENT_STATUS_CODES = new Set([
    401, // Handled by session-expired modal
]);

/**
 * Endpoints, die keine Error-Toasts anzeigen sollen
 * (z.B. Login-Versuche, bei denen Fehler erwartet werden)
 */
const SILENT_ENDPOINTS = [
    '/auth/login',
    '/auth/verify-2fa',
    '/auth/refresh',
    '/extracted-data/', // 404 is expected for new documents without extracted data
];

/**
 * Rate-Limiter für Error-Toasts
 * Verhindert Toast-Spam bei schnellen aufeinanderfolgenden Fehlern
 */
const toastRateLimiter = {
    lastToastTime: new Map<string, number>(),
    minIntervalMs: 3000, // Mindestabstand zwischen gleichen Toasts

    shouldShow(key: string): boolean {
        const now = Date.now();
        const lastTime = this.lastToastTime.get(key) || 0;

        if (now - lastTime < this.minIntervalMs) {
            return false;
        }

        this.lastToastTime.set(key, now);
        return true;
    },

    clear(): void {
        this.lastToastTime.clear();
    },
};

/**
 * Extrahiert einen lesbaren Fehlertext aus der API-Antwort
 */
function extractErrorMessage(error: AxiosError): string | null {
    const data = error.response?.data as Record<string, unknown> | undefined;

    if (!data) return null;

    // FastAPI-Format: {"detail": "message"} oder {"detail": [...]}
    if (typeof data.detail === 'string') {
        return data.detail;
    }

    // Pydantic Validation Errors
    if (Array.isArray(data.detail)) {
        const messages = data.detail
            .map((err: { msg?: string; message?: string }) => err.msg || err.message)
            .filter(Boolean);
        return messages.length > 0 ? messages.join('. ') : null;
    }

    // Generisches message-Feld
    if (typeof data.message === 'string') {
        return data.message;
    }

    // Generisches error-Feld
    if (typeof data.error === 'string') {
        return data.error;
    }

    return null;
}

/**
 * Zeigt einen Error-Toast für den gegebenen API-Fehler
 */
export function showApiErrorToast(error: AxiosError): void {
    // Request-URL prüfen
    const url = error.config?.url || '';

    // Silent Endpoints ignorieren
    if (SILENT_ENDPOINTS.some(endpoint => url.includes(endpoint))) {
        return;
    }

    // Status-Code ermitteln
    const status = error.response?.status;

    // Silent Status Codes ignorieren
    if (status && SILENT_STATUS_CODES.has(status)) {
        return;
    }

    // Toast-Key für Rate-Limiting
    const toastKey = status?.toString() || error.code || 'UNKNOWN';

    // Rate-Limiting prüfen
    if (!toastRateLimiter.shouldShow(toastKey)) {
        return;
    }

    // Fehler-Nachricht ermitteln
    let errorInfo: { title: string; description: string };

    if (!error.response) {
        // Netzwerk-Fehler (keine Response)
        if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
            errorInfo = ERROR_MESSAGES.TIMEOUT;
        } else {
            errorInfo = ERROR_MESSAGES.NETWORK_ERROR;
        }
    } else if (status && ERROR_MESSAGES[status]) {
        // Bekannter HTTP-Status
        errorInfo = { ...ERROR_MESSAGES[status] };

        // Fix 7: Bei 429 Rate-Limit den Retry-After Header anzeigen
        // P2 Fix (Iteration 14): Auch HTTP-Datum Format unterstützen (RFC 7231)
        if (status === 429) {
            const retryAfter = error.response?.headers?.['retry-after'];
            if (retryAfter) {
                let seconds = parseInt(retryAfter, 10);
                // P2 Fix: Falls keine Zahl, versuche HTTP-Datum zu parsen
                if (isNaN(seconds)) {
                    const date = new Date(retryAfter);
                    if (!isNaN(date.getTime())) {
                        seconds = Math.max(0, Math.ceil((date.getTime() - Date.now()) / 1000));
                    }
                }
                if (!isNaN(seconds) && seconds > 0) {
                    errorInfo.description = `Bitte warten Sie ${seconds} Sekunde${seconds !== 1 ? 'n' : ''}, bevor Sie es erneut versuchen.`;
                }
            }
        } else {
            // Versuche, spezifischere Nachricht aus Response zu extrahieren
            const customMessage = extractErrorMessage(error);
            if (customMessage) {
                errorInfo.description = customMessage;
            }
        }
    } else {
        // Unbekannter Fehler
        errorInfo = {
            title: 'Fehler',
            description: extractErrorMessage(error) || `Ein unerwarteter Fehler ist aufgetreten (${status || 'Unbekannt'}).`,
        };
    }

    // Prüfen ob der Fehler wiederholbar ist
    const RETRYABLE_STATUS_CODES = new Set([500, 502, 503, 504, 429]);
    const isNetworkError = !error.response && (
        error.code === 'ECONNABORTED' ||
        error.code === 'ETIMEDOUT' ||
        error.code === 'ERR_NETWORK'
    );
    const isRetryable = isNetworkError || (status !== undefined && RETRYABLE_STATUS_CODES.has(status));

    // Toast anzeigen
    if (isRetryable && error.config) {
        // Referenz auf die ursprüngliche Konfiguration für den Retry-Handler
        const originalConfig = error.config;

        // Sonner direkt nutzen für nativen Action-Button-Support
        sonnerToast.error(errorInfo.title, {
            description: errorInfo.description,
            action: {
                label: 'Erneut versuchen',
                onClick: () => {
                    apiClient.request(originalConfig);
                },
            },
        });
    } else {
        toast({
            title: errorInfo.title,
            description: errorInfo.description,
            variant: 'destructive',
        });
    }
}

/**
 * Initialisiert den globalen Error-Handler
 * Wird automatisch beim Import aufgerufen
 */
export function initApiErrorHandler(): void {
    // Event-Listener für globale API-Fehler
    window.addEventListener('api-error', ((event: CustomEvent<AxiosError>) => {
        showApiErrorToast(event.detail);
    }) as EventListener);
}

/**
 * Dispatcht einen API-Fehler-Event
 */
export function dispatchApiError(error: AxiosError): void {
    window.dispatchEvent(new CustomEvent('api-error', { detail: error }));
}

// Export der Rate-Limiter-Funktionen für Tests
export const _testUtils = {
    toastRateLimiter,
    extractErrorMessage,
};

/**
 * Alias for backwards compatibility - some files import handleApiError
 * This is a function that shows the toast and re-throws the error for handling
 *
 * P2 FIX (Iteration 12): Spezifischer AxiosError Check statt unsicherem Cast.
 * - AxiosError wird korrekt an showApiErrorToast weitergegeben
 * - Normale Error-Instanzen werden nur geloggt (kein Toast-Spam)
 * - Beide Fälle werfen den ursprünglichen Fehler weiter
 */
export function handleApiError(error: unknown): never {
    if (error instanceof AxiosError) {
        // Echter AxiosError mit response/config - zeige Toast
        showApiErrorToast(error);
    } else if (error instanceof Error) {
        // Normaler Error (z.B. TypeError, ReferenceError) - nur loggen
        // KEIN Toast, da diese Fehler nicht vom API kommen
        logger.error('[handleApiError] Non-Axios error:', error.message);
    } else {
        // P0 Fix: Catch-all für null, undefined, primitive (string, number, etc.)
        // Verhindert silent throws ohne jegliches Logging
        logger.error(
            '[handleApiError] Unknown error type:',
            error === null ? 'null' : error === undefined ? 'undefined' : String(error)
        );
    }
    throw error;
}
