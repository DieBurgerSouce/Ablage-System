import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AxiosError, AxiosHeaders } from 'axios';
import {
    showApiErrorToast,
    initApiErrorHandler,
    dispatchApiError,
    _testUtils,
} from '../error-toast-handler';

// Mock the toast function
vi.mock('@/components/ui/use-toast', () => ({
    toast: vi.fn(),
}));

import { toast } from '@/components/ui/use-toast';

// Helper to create Axios errors
function createAxiosError(
    status: number | null,
    data: Record<string, unknown> = {},
    url: string = '/api/test'
): AxiosError {
    const error = new AxiosError('Test error');
    error.config = {
        url,
        headers: new AxiosHeaders(),
    };

    if (status !== null) {
        error.response = {
            status,
            statusText: 'Error',
            data,
            headers: {},
            config: error.config,
        };
    }

    return error;
}

describe('error-toast-handler', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        _testUtils.toastRateLimiter.clear();
    });

    describe('showApiErrorToast', () => {
        describe('HTTP Status Codes', () => {
            it('zeigt Toast für 400 Bad Request', () => {
                const error = createAxiosError(400);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Ungültige Anfrage',
                    description: 'Die Anfrage war fehlerhaft. Bitte überprüfen Sie Ihre Eingaben.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für 403 Forbidden', () => {
                const error = createAxiosError(403);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Zugriff verweigert',
                    description: 'Sie haben keine Berechtigung für diese Aktion.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für 404 Not Found', () => {
                const error = createAxiosError(404);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Nicht gefunden',
                    description: 'Die angeforderte Ressource wurde nicht gefunden.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für 409 Conflict', () => {
                const error = createAxiosError(409);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Konflikt',
                    description: 'Die Anfrage konnte wegen eines Konflikts nicht ausgeführt werden.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für 422 Validation Error', () => {
                const error = createAxiosError(422);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Validierungsfehler',
                    description: 'Die eingegebenen Daten sind ungültig.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für 429 Rate Limit', () => {
                const error = createAxiosError(429);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Zu viele Anfragen',
                    description: 'Sie haben zu viele Anfragen gesendet. Bitte warten Sie einen Moment.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für 500 Server Error', () => {
                const error = createAxiosError(500);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Server-Fehler',
                    description: 'Ein interner Server-Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für 502 Bad Gateway', () => {
                const error = createAxiosError(502);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Server nicht erreichbar',
                    description: 'Der Server ist vorübergehend nicht erreichbar.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für 503 Service Unavailable', () => {
                const error = createAxiosError(503);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Dienst nicht verfügbar',
                    description: 'Der Dienst ist vorübergehend nicht verfügbar. Bitte versuchen Sie es später erneut.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für 504 Gateway Timeout', () => {
                const error = createAxiosError(504);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Gateway-Zeitüberschreitung',
                    description: 'Der Server hat nicht rechtzeitig geantwortet.',
                    variant: 'destructive',
                });
            });
        });

        describe('Silent Status Codes', () => {
            it('ignoriert 401 Unauthorized (wird von Session-Modal behandelt)', () => {
                const error = createAxiosError(401);
                showApiErrorToast(error);

                expect(toast).not.toHaveBeenCalled();
            });
        });

        describe('Silent Endpoints', () => {
            it('ignoriert /auth/login Fehler', () => {
                const error = createAxiosError(400, {}, '/api/v1/auth/login');
                showApiErrorToast(error);

                expect(toast).not.toHaveBeenCalled();
            });

            it('ignoriert /auth/verify-2fa Fehler', () => {
                const error = createAxiosError(400, {}, '/api/v1/auth/verify-2fa');
                showApiErrorToast(error);

                expect(toast).not.toHaveBeenCalled();
            });

            it('ignoriert /auth/refresh Fehler', () => {
                const error = createAxiosError(400, {}, '/api/v1/auth/refresh');
                showApiErrorToast(error);

                expect(toast).not.toHaveBeenCalled();
            });
        });

        describe('Network Errors', () => {
            it('zeigt Toast für Netzwerkfehler (keine Response)', () => {
                const error = createAxiosError(null);
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Keine Verbindung',
                    description: 'Keine Verbindung zum Server. Bitte prüfen Sie Ihre Internetverbindung.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für Timeout', () => {
                const error = createAxiosError(null);
                error.code = 'ECONNABORTED';
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Zeitüberschreitung',
                    description: 'Die Anfrage hat zu lange gedauert. Bitte versuchen Sie es erneut.',
                    variant: 'destructive',
                });
            });

            it('zeigt Toast für ETIMEDOUT', () => {
                const error = createAxiosError(null);
                error.code = 'ETIMEDOUT';
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Zeitüberschreitung',
                    description: 'Die Anfrage hat zu lange gedauert. Bitte versuchen Sie es erneut.',
                    variant: 'destructive',
                });
            });
        });

        describe('Custom Error Messages', () => {
            it('verwendet detail aus FastAPI-Response', () => {
                const error = createAxiosError(400, { detail: 'Spezifischer Fehler' });
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Ungültige Anfrage',
                    description: 'Spezifischer Fehler',
                    variant: 'destructive',
                });
            });

            it('verarbeitet Pydantic Validation Errors', () => {
                const error = createAxiosError(422, {
                    detail: [
                        { msg: 'Feld ist erforderlich' },
                        { msg: 'Ungültiges Format' },
                    ],
                });
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Validierungsfehler',
                    description: 'Feld ist erforderlich. Ungültiges Format',
                    variant: 'destructive',
                });
            });

            it('verwendet message-Feld als Fallback', () => {
                const error = createAxiosError(400, { message: 'Benutzerdefinierte Nachricht' });
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Ungültige Anfrage',
                    description: 'Benutzerdefinierte Nachricht',
                    variant: 'destructive',
                });
            });

            it('verwendet error-Feld als Fallback', () => {
                const error = createAxiosError(400, { error: 'Fehlertext' });
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Ungültige Anfrage',
                    description: 'Fehlertext',
                    variant: 'destructive',
                });
            });
        });

        describe('Unknown Status Codes', () => {
            it('zeigt generischen Toast für unbekannte Status', () => {
                const error = createAxiosError(418); // I'm a teapot
                showApiErrorToast(error);

                expect(toast).toHaveBeenCalledWith({
                    title: 'Fehler',
                    description: 'Ein unerwarteter Fehler ist aufgetreten (418).',
                    variant: 'destructive',
                });
            });
        });
    });

    describe('Rate Limiting', () => {
        it('verhindert Toast-Spam für gleiche Fehler', () => {
            const error = createAxiosError(500);

            showApiErrorToast(error);
            showApiErrorToast(error);
            showApiErrorToast(error);

            // Nur ein Toast sollte angezeigt werden
            expect(toast).toHaveBeenCalledTimes(1);
        });

        it('erlaubt verschiedene Fehlertypen nacheinander', () => {
            showApiErrorToast(createAxiosError(500));
            showApiErrorToast(createAxiosError(404));
            showApiErrorToast(createAxiosError(403));

            expect(toast).toHaveBeenCalledTimes(3);
        });

        it('erlaubt gleichen Fehler nach Rate-Limit-Intervall', async () => {
            vi.useFakeTimers();

            const error = createAxiosError(500);

            showApiErrorToast(error);
            expect(toast).toHaveBeenCalledTimes(1);

            // Advance time past rate limit (3000ms)
            vi.advanceTimersByTime(3500);

            showApiErrorToast(error);
            expect(toast).toHaveBeenCalledTimes(2);

            vi.useRealTimers();
        });
    });

    describe('extractErrorMessage', () => {
        const { extractErrorMessage } = _testUtils;

        it('extrahiert string detail', () => {
            const error = createAxiosError(400, { detail: 'Test Fehler' });
            expect(extractErrorMessage(error)).toBe('Test Fehler');
        });

        it('extrahiert Array detail (Pydantic)', () => {
            const error = createAxiosError(422, {
                detail: [{ msg: 'Error 1' }, { msg: 'Error 2' }],
            });
            expect(extractErrorMessage(error)).toBe('Error 1. Error 2');
        });

        it('extrahiert message Feld', () => {
            const error = createAxiosError(400, { message: 'Message Fehler' });
            expect(extractErrorMessage(error)).toBe('Message Fehler');
        });

        it('extrahiert error Feld', () => {
            const error = createAxiosError(400, { error: 'Error Feld' });
            expect(extractErrorMessage(error)).toBe('Error Feld');
        });

        it('gibt null zurück wenn keine Nachricht vorhanden', () => {
            const error = createAxiosError(400, {});
            expect(extractErrorMessage(error)).toBeNull();
        });

        it('gibt null zurück wenn keine Response vorhanden', () => {
            const error = createAxiosError(null);
            expect(extractErrorMessage(error)).toBeNull();
        });
    });

    describe('Event System', () => {
        afterEach(() => {
            // Clean up event listeners
            window.removeEventListener('api-error', vi.fn());
        });

        it('initApiErrorHandler registriert globalen Event-Listener', () => {
            const addEventListenerSpy = vi.spyOn(window, 'addEventListener');

            initApiErrorHandler();

            expect(addEventListenerSpy).toHaveBeenCalledWith('api-error', expect.any(Function));
        });

        it('dispatchApiError sendet Custom Event', () => {
            const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent');
            const error = createAxiosError(500);

            dispatchApiError(error);

            expect(dispatchEventSpy).toHaveBeenCalledWith(
                expect.objectContaining({
                    type: 'api-error',
                    detail: error,
                })
            );
        });
    });
});
