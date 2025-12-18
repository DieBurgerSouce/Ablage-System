import axios from 'axios';

// API Base URL from environment variable with fallback
// Use relative URL to go through nginx proxy (works in both dev and prod)
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

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

// Response Interceptor
apiClient.interceptors.response.use(
    (response) => {
        return response;
    },
    async (error) => {
        const originalRequest = error.config;

        // Handle 401 Unauthorized
        if (error.response?.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;

            try {
                // Dynamically import authService to avoid circular dependency
                const { authService } = await import('./services/auth');
                const newToken = await authService.refreshToken();

                originalRequest.headers.Authorization = `Bearer ${newToken}`;
                return apiClient(originalRequest);
            } catch (refreshError) {
                // Refresh failed, logout user
                console.error('Token refresh failed:', refreshError);
                sessionStorage.removeItem('auth_token');
                sessionStorage.removeItem('refresh_token');
                sessionStorage.removeItem('user');
                window.location.href = '/login';
                return Promise.reject(refreshError);
            }
        }
        return Promise.reject(error);
    }
);
