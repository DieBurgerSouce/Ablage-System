/**
 * API Error Types
 *
 * Typen für API-Fehler und Fehlerbehandlung.
 * Alle Fehlermeldungen sind auf Deutsch.
 */

/**
 * Standard API error response from backend
 */
export interface ApiErrorResponse {
    detail: string | ApiErrorDetail;
    status_code?: number;
}

/**
 * Detailed error information
 */
export interface ApiErrorDetail {
    message: string;
    code: string;
    field?: string;
    context?: Record<string, unknown>;
}

/**
 * Validation error (422)
 */
export interface ValidationErrorResponse {
    detail: ValidationError[];
}

export interface ValidationError {
    loc: Array<string | number>;
    msg: string;
    type: string;
}

/**
 * Known API error codes
 */
export type ApiErrorCode =
    | 'AUTHENTICATION_REQUIRED'
    | 'INVALID_CREDENTIALS'
    | 'TOKEN_EXPIRED'
    | 'FORBIDDEN'
    | 'NOT_FOUND'
    | 'VALIDATION_ERROR'
    | 'DUPLICATE_ENTRY'
    | 'RATE_LIMIT_EXCEEDED'
    | 'SERVER_ERROR'
    | 'SERVICE_UNAVAILABLE'
    | 'OCR_PROCESSING_FAILED'
    | 'GPU_UNAVAILABLE'
    | 'FILE_TOO_LARGE'
    | 'INVALID_FILE_TYPE';

/**
 * HTTP status codes with German descriptions
 */
export const HTTP_STATUS_MESSAGES: Record<number, string> = {
    400: 'Ungültige Anfrage',
    401: 'Authentifizierung erforderlich',
    403: 'Zugriff verweigert',
    404: 'Nicht gefunden',
    409: 'Konflikt - Ressource existiert bereits',
    413: 'Datei zu groß',
    422: 'Validierungsfehler',
    429: 'Zu viele Anfragen',
    500: 'Interner Serverfehler',
    502: 'Server nicht erreichbar',
    503: 'Service nicht verfügbar',
    504: 'Zeitüberschreitung',
};

/**
 * Error code messages in German
 */
export const ERROR_CODE_MESSAGES: Record<ApiErrorCode, string> = {
    AUTHENTICATION_REQUIRED: 'Bitte melden Sie sich an',
    INVALID_CREDENTIALS: 'Ungültige Anmeldedaten',
    TOKEN_EXPIRED: 'Sitzung abgelaufen - bitte erneut anmelden',
    FORBIDDEN: 'Sie haben keine Berechtigung für diese Aktion',
    NOT_FOUND: 'Die angeforderte Ressource wurde nicht gefunden',
    VALIDATION_ERROR: 'Die eingegebenen Daten sind ungültig',
    DUPLICATE_ENTRY: 'Ein Eintrag mit diesen Daten existiert bereits',
    RATE_LIMIT_EXCEEDED: 'Zu viele Anfragen - bitte warten Sie einen Moment',
    SERVER_ERROR: 'Ein unerwarteter Fehler ist aufgetreten',
    SERVICE_UNAVAILABLE: 'Der Dienst ist vorübergehend nicht verfügbar',
    OCR_PROCESSING_FAILED: 'Die OCR-Verarbeitung ist fehlgeschlagen',
    GPU_UNAVAILABLE: 'GPU nicht verfügbar - Fallback auf CPU',
    FILE_TOO_LARGE: 'Die Datei ist zu groß (max. 50 MB)',
    INVALID_FILE_TYPE: 'Ungültiger Dateityp',
};

/**
 * Custom error class for API errors
 */
export class ApiError extends Error {
    public readonly statusCode: number;
    public readonly code: ApiErrorCode | string;
    public readonly details?: unknown;

    constructor(
        message: string,
        statusCode: number,
        code: ApiErrorCode | string = 'SERVER_ERROR',
        details?: unknown
    ) {
        super(message);
        this.name = 'ApiError';
        this.statusCode = statusCode;
        this.code = code;
        this.details = details;
    }

    /**
     * Get German message for this error
     */
    getGermanMessage(): string {
        if (this.code in ERROR_CODE_MESSAGES) {
            return ERROR_CODE_MESSAGES[this.code as ApiErrorCode];
        }
        if (this.statusCode in HTTP_STATUS_MESSAGES) {
            return HTTP_STATUS_MESSAGES[this.statusCode];
        }
        return this.message;
    }
}

/**
 * Type guard to check if an error is an ApiError
 */
export function isApiError(error: unknown): error is ApiError {
    return error instanceof ApiError;
}

/**
 * Type guard for validation errors
 */
export function isValidationError(error: unknown): error is ValidationErrorResponse {
    return (
        typeof error === 'object' &&
        error !== null &&
        'detail' in error &&
        Array.isArray((error as ValidationErrorResponse).detail)
    );
}

/**
 * Extract user-friendly error message
 */
export function getErrorMessage(error: unknown): string {
    if (isApiError(error)) {
        return error.getGermanMessage();
    }

    if (error instanceof Error) {
        return error.message;
    }

    if (typeof error === 'string') {
        return error;
    }

    return 'Ein unerwarteter Fehler ist aufgetreten';
}
