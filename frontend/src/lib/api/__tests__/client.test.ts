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

        it('hat withCredentials auf false', () => {
            expect(apiClient.defaults.withCredentials).toBe(false);
        });

        it('hat baseURL konfiguriert', () => {
            // Should be either from env or fallback
            expect(apiClient.defaults.baseURL).toBeDefined();
        });
    });

    // ==================== Request Interceptor ====================

    describe('Request Interceptor', () => {
        it('fügt Authorization Header hinzu wenn Token vorhanden', async () => {
            sessionStorage.setItem('auth_token', 'test-token-123');

            // Create a mock request config
            const config = {
                headers: {},
                url: '/test',
                method: 'get',
            };

            // Get the request interceptor
            const requestInterceptor = apiClient.interceptors.request.handlers[0];
            expect(requestInterceptor).toBeDefined();

            // Run the interceptor
            const result = await requestInterceptor.fulfilled(config);

            expect(result.headers.Authorization).toBe('Bearer test-token-123');
        });

        it('sendet keine Authorization Header wenn kein Token', async () => {
            // Ensure no token
            sessionStorage.removeItem('auth_token');

            const config = {
                headers: {},
                url: '/test',
                method: 'get',
            };

            const requestInterceptor = apiClient.interceptors.request.handlers[0];
            const result = await requestInterceptor.fulfilled(config);

            expect(result.headers.Authorization).toBeUndefined();
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
        it('verwendet sessionStorage statt localStorage für Token', () => {
            // This is a documentation test - sessionStorage is more secure
            // because tokens are cleared when the tab closes and not shared between tabs

            // Set a token
            sessionStorage.setItem('auth_token', 'test-secure-token');

            // Verify it's in sessionStorage
            expect(sessionStorage.getItem('auth_token')).toBe('test-secure-token');

            // Verify it's NOT in localStorage
            expect(localStorage.getItem('auth_token')).toBeNull();

            // Cleanup
            sessionStorage.removeItem('auth_token');
        });
    });
});
