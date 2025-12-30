import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { showApiErrorToast } from './error-toast-handler';

// API Base URL from environment variable with fallback
// Use relative URL to go through nginx proxy (works in both dev and prod)
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

// ============================================================================
// RETRY CONFIGURATION
// ============================================================================
const RETRY_CONFIG = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 10000,
  // Retryable HTTP status codes (transiente Fehler)
  retryableStatuses: [408, 429, 500, 502, 503, 504],
  // Retryable error codes (Netzwerkfehler)
  retryableErrorCodes: ['ECONNABORTED', 'ENOTFOUND', 'ECONNREFUSED', 'ECONNRESET', 'ETIMEDOUT', 'ERR_NETWORK'],
};

// Extended request config with retry metadata
interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retryCount?: number;
  _retryDelayMs?: number;
  _isRetry?: boolean;
}

/**
 * Calculate delay with exponential backoff and jitter
 */
function calculateRetryDelay(retryCount: number): number {
  // Exponential backoff: 1s, 2s, 4s, 8s...
  const exponentialDelay = RETRY_CONFIG.baseDelayMs * Math.pow(2, retryCount);
  // Add jitter (0-500ms) to prevent thundering herd
  const jitter = Math.random() * 500;
  // Cap at max delay
  return Math.min(exponentialDelay + jitter, RETRY_CONFIG.maxDelayMs);
}

/**
 * Check if error is retryable
 */
function isRetryableError(error: AxiosError): boolean {
  // Network errors (no response)
  if (!error.response) {
    const code = error.code || '';
    return RETRY_CONFIG.retryableErrorCodes.includes(code);
  }

  // HTTP status-based retries
  return RETRY_CONFIG.retryableStatuses.includes(error.response.status);
}

/**
 * Sleep utility
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Create Axios instance with default config
// Use direct backend URL to avoid nginx proxy issues
export const apiClient = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: 10000,
    withCredentials: false, // No cookies for cross-origin
});

// Request Interceptor
// SECURITY NOTE: sessionStorage ist sicherer als localStorage, da Tokens
// bei Tab-Schließung gelöscht werden und nicht zwischen Tabs geteilt werden.
// Für maximale Sicherheit sollten Tokens als httpOnly Cookies vom Backend
// gesetzt werden. Dies erfordert:
// 1. Backend: Set-Cookie Header mit httpOnly, Secure, SameSite=Strict
// 2. Frontend: credentials: 'include' bei fetch/axios
// 3. CSRF-Token für state-changing requests
// Phase 1.1: Migration von localStorage zu sessionStorage (XSS-Mitigation)
apiClient.interceptors.request.use(
    (config) => {
        // Get token from sessionStorage (sicherer als localStorage)
        const token = sessionStorage.getItem('auth_token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Response Interceptor with Retry Logic and Rate Limit Handling
apiClient.interceptors.response.use(
    (response) => {
        return response;
    },
    async (error: AxiosError) => {
        const originalRequest = error.config as RetryableRequestConfig;

        if (!originalRequest) {
            return Promise.reject(error);
        }

        // Initialize retry count
        originalRequest._retryCount = originalRequest._retryCount || 0;

        // Handle 401 Unauthorized (Auth-spezifisch, kein Retry)
        if (error.response?.status === 401 && !originalRequest._isRetry) {
            originalRequest._isRetry = true;

            try {
                // Dynamically import authService to avoid circular dependency
                const { authService } = await import('./services/auth');
                const newToken = await authService.refreshToken();

                originalRequest.headers.Authorization = `Bearer ${newToken}`;
                return apiClient(originalRequest);
            } catch (refreshError) {
                // Refresh failed - emit event for session expired modal
                // SECURITY FIX Phase 11.4: Only log error details in development
                if (import.meta.env.DEV) {
                    console.error('Token refresh failed:', refreshError);
                }
                sessionStorage.removeItem('auth_token');
                sessionStorage.removeItem('refresh_token');
                sessionStorage.removeItem('user');

                // Store current path for redirect after re-login
                sessionStorage.setItem('redirect_after_login', window.location.pathname);

                // Dispatch custom event for session expired modal
                window.dispatchEvent(new CustomEvent('session-expired', {
                    detail: { redirectPath: window.location.pathname }
                }));

                return Promise.reject(refreshError);
            }
        }

        // Handle 429 Rate Limit with Retry-After header
        if (error.response?.status === 429) {
            const retryAfter = error.response.headers['retry-after'];
            if (retryAfter && originalRequest._retryCount < RETRY_CONFIG.maxRetries) {
                const delayMs = parseInt(retryAfter, 10) * 1000 || calculateRetryDelay(originalRequest._retryCount);
                originalRequest._retryCount += 1;

                // SECURITY FIX Phase 11.4: Only log retry details in development
                if (import.meta.env.DEV) {
                    console.warn(
                        `Rate limited (429). Retrying in ${Math.round(delayMs / 1000)}s... ` +
                        `(Attempt ${originalRequest._retryCount}/${RETRY_CONFIG.maxRetries})`
                    );
                }

                await sleep(delayMs);
                return apiClient(originalRequest);
            }
        }

        // Handle retryable errors (transiente Fehler)
        if (
            isRetryableError(error) &&
            originalRequest._retryCount < RETRY_CONFIG.maxRetries &&
            // Only retry idempotent methods by default
            ['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE'].includes(originalRequest.method?.toUpperCase() || '')
        ) {
            originalRequest._retryCount += 1;
            const delayMs = calculateRetryDelay(originalRequest._retryCount - 1);

            // SECURITY FIX Phase 11.4: Only log retry details in development
            if (import.meta.env.DEV) {
                console.warn(
                    `Request failed with ${error.response?.status || error.code}. ` +
                    `Retrying in ${Math.round(delayMs / 1000)}s... ` +
                    `(Attempt ${originalRequest._retryCount}/${RETRY_CONFIG.maxRetries})`
                );
            }

            await sleep(delayMs);
            return apiClient(originalRequest);
        }

        // Show error toast for failed requests (after retries exhausted)
        // This handles K3: Error Toasts für API-Fehler
        showApiErrorToast(error);

        return Promise.reject(error);
    }
);
