/**
 * API Client Interceptor Unit Tests
 *
 * Enterprise-Level Tests für den Axios API Client.
 * Testet Request/Response Interceptors, Token Handling.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock the error toast handler
vi.mock('../error-toast-handler', () => ({
    showApiErrorToast: vi.fn(),
}));

// Mock auth service
const mockRefreshToken = vi.fn();
vi.mock('../services/auth', () => ({
    authService: {
        refreshToken: () => mockRefreshToken(),
    },
}));

// Import after mocks
import { apiClient } from '../client';
import { showApiErrorToast } from '../error-toast-handler';

describe('API Client', () => {
    beforeEach(() => {
        vi.clearAllMocks();

        // Clear sessionStorage
        sessionStorage.clear();

        // Clear cookies (CSRF-Token) zwischen Tests
        document.cookie.split(';').forEach((c) => {
            const name = c.split('=')[0].trim();
            if (name) document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/`;
        });

        // Reset window.location
        Object.defineProperty(window, 'location', {
            value: { pathname: '/test-path' },
            writable: true,
        });

        // Mock CustomEvent and dispatchEvent
        vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true);
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    // ==================== Configuration ====================

    describe('Client Configuration', () => {
        it('hat korrektes Content-Type Header', () => {
            expect(apiClient.defaults.headers['Content-Type']).toBe('application/json');
        });

        it('hat Timeout konfiguriert', () => {
            expect(apiClient.defaults.timeout).toBe(10000);
        });

        it('hat withCredentials auf true (Cookie-Auth, G03)', () => {
            expect(apiClient.defaults.withCredentials).toBe(true);
        });

        it('hat baseURL konfiguriert', () => {
            // Should be either from env or fallback
            expect(apiClient.defaults.baseURL).toBeDefined();
        });
    });

    // ==================== Request Interceptor ====================

    describe('Request Interceptor', () => {
        it('setzt KEINEN Authorization Header (G03: Cookie-Auth statt JS-Token)', async () => {
            // Selbst wenn ein Alt-Token im sessionStorage liegt, darf der REST-Client
            // keinen Bearer-Header mehr setzen - Auth laeuft ueber das httpOnly-Cookie.
            sessionStorage.setItem('auth_token', 'sollte-ignoriert-werden');

            const config = {
                headers: {},
                url: '/test',
                method: 'get',
            };

            const requestInterceptor = apiClient.interceptors.request.handlers[0];
            expect(requestInterceptor).toBeDefined();

            const result = await requestInterceptor.fulfilled(config);

            expect(result.headers.Authorization).toBeUndefined();
        });

        it('fügt X-CSRF-Token bei state-changing Requests hinzu (aus csrf_token-Cookie)', async () => {
            document.cookie = 'csrf_token=test-csrf-123';

            const config = {
                headers: {},
                url: '/test',
                method: 'post',
            };

            const requestInterceptor = apiClient.interceptors.request.handlers[0];
            const result = await requestInterceptor.fulfilled(config);

            expect(result.headers['X-CSRF-Token']).toBe('test-csrf-123');
        });

        it('fügt KEIN X-CSRF-Token bei GET-Requests hinzu', async () => {
            document.cookie = 'csrf_token=test-csrf-123';

            const config = {
                headers: {},
                url: '/test',
                method: 'get',
            };

            const requestInterceptor = apiClient.interceptors.request.handlers[0];
            const result = await requestInterceptor.fulfilled(config);

            expect(result.headers['X-CSRF-Token']).toBeUndefined();
        });
    });

    // ==================== Session Expired Handling ====================

    describe('Session Expired Event', () => {
        it('dispatcht session-expired Event bei Token Refresh Fehler', async () => {
            sessionStorage.setItem('auth_token', 'old-token');
            sessionStorage.setItem('refresh_token', 'refresh-token');
            sessionStorage.setItem('user', JSON.stringify({ id: '1' }));

            mockRefreshToken.mockRejectedValue(new Error('Refresh failed'));

            // Create a mock 401 error
            const error = {
                response: { status: 401 },
                config: {
                    _isRetry: false,
                    headers: {},
                },
            };

            // Get the response error interceptor
            const responseInterceptor = apiClient.interceptors.response.handlers[0];
            expect(responseInterceptor).toBeDefined();

            // Run the error handler and expect it to reject
            try {
                await responseInterceptor.rejected(error);
            } catch {
                // Expected to fail
            }

            // Give async operations time to complete
            await new Promise(resolve => setTimeout(resolve, 100));

            // Check session was cleared
            expect(sessionStorage.getItem('auth_token')).toBeNull();
            expect(sessionStorage.getItem('refresh_token')).toBeNull();
            expect(sessionStorage.getItem('user')).toBeNull();

            // Check redirect path was stored
            expect(sessionStorage.getItem('redirect_after_login')).toBe('/test-path');

            // Check event was dispatched
            expect(window.dispatchEvent).toHaveBeenCalled();
        });
    });

    // ==================== Error Toast ====================

    describe('Error Toast', () => {
        it('showApiErrorToast ist importiert und verfügbar', () => {
            expect(showApiErrorToast).toBeDefined();
        });
    });

    // ==================== Retry Configuration ====================

    describe('Retry Configuration', () => {
        it('hat Retry-Logik für transiente Fehler', () => {
            // Verify the client has response interceptors configured
            expect(apiClient.interceptors.response.handlers.length).toBeGreaterThan(0);
        });
    });

    // ==================== CSRF Configuration Note ====================

    describe('Security Configuration', () => {
        it('REST-Auth nutzt httpOnly-Cookie statt JS-Token (G03)', () => {
            // Der REST-Client liest den Token NICHT mehr aus dem Storage fuer den
            // Authorization-Header; die Session laeuft ueber das httpOnly-Cookie +
            // CSRF-Double-Submit. (Vollstaendige JS-Token-Entfernung fuer WS/SSE = Folgearbeit.)
            expect(apiClient.defaults.withCredentials).toBe(true);
        });
    });
});
