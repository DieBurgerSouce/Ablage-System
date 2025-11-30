/**
 * Ablage-System API Client
 * Centralized API communication with authentication, error handling, and retry logic
 */

// Configuration
const API_CONFIG = {
    BASE_URL: window.location.hostname === 'localhost'
        ? 'http://localhost:8000'
        : window.location.origin,
    API_VERSION: '/api/v1',
    TIMEOUT: 30000, // 30 seconds
    MAX_RETRIES: 3,
    RETRY_DELAY: 1000 // 1 second
};

/**
 * API Client class with interceptors and error handling
 */
class APIClient {
    constructor() {
        this.baseURL = API_CONFIG.BASE_URL;
        this.apiVersion = API_CONFIG.API_VERSION;
        this.timeout = API_CONFIG.TIMEOUT;
        this.maxRetries = API_CONFIG.MAX_RETRIES;
        this.retryDelay = API_CONFIG.RETRY_DELAY;

        // Request interceptors
        this.requestInterceptors = [];
        this.responseInterceptors = [];

        // Add default auth interceptor
        this.addRequestInterceptor(this.authInterceptor.bind(this));
    }

    /**
     * Add authentication headers to requests
     */
    authInterceptor(config) {
        const token = localStorage.getItem('access_token');
        if (token && !config.skipAuth) {
            config.headers = config.headers || {};
            config.headers['Authorization'] = `Bearer ${token}`;
        }
        return config;
    }

    /**
     * Add request interceptor
     */
    addRequestInterceptor(interceptor) {
        this.requestInterceptors.push(interceptor);
    }

    /**
     * Add response interceptor
     */
    addResponseInterceptor(interceptor) {
        this.responseInterceptors.push(interceptor);
    }

    /**
     * Apply request interceptors
     */
    async applyRequestInterceptors(config) {
        let modifiedConfig = { ...config };
        for (const interceptor of this.requestInterceptors) {
            modifiedConfig = await interceptor(modifiedConfig);
        }
        return modifiedConfig;
    }

    /**
     * Apply response interceptors
     */
    async applyResponseInterceptors(response) {
        let modifiedResponse = response;
        for (const interceptor of this.responseInterceptors) {
            modifiedResponse = await interceptor(modifiedResponse);
        }
        return modifiedResponse;
    }

    /**
     * Build full URL
     */
    buildURL(endpoint, includeApiVersion = true) {
        const base = this.baseURL;
        const version = includeApiVersion ? this.apiVersion : '';
        return `${base}${version}${endpoint}`;
    }

    /**
     * Sleep utility for retry delay
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Core request method with retry logic
     */
    async request(endpoint, options = {}, retryCount = 0) {
        try {
            // Apply request interceptors
            const config = await this.applyRequestInterceptors({
                ...options,
                endpoint
            });

            // Build URL
            const url = this.buildURL(
                config.endpoint,
                config.includeApiVersion !== false
            );

            // Create abort controller for timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.timeout);

            // Make request
            const response = await fetch(url, {
                ...config,
                signal: controller.signal,
                headers: {
                    ...config.headers
                }
            });

            clearTimeout(timeoutId);

            // Handle response
            let data;
            const contentType = response.headers.get('content-type');

            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                data = await response.text();
            }

            // Check for errors
            if (!response.ok) {
                // Handle authentication errors
                if (response.status === 401) {
                    // Try to refresh token
                    const refreshed = await this.handleTokenRefresh();
                    if (refreshed && retryCount < this.maxRetries) {
                        await this.sleep(this.retryDelay);
                        return this.request(endpoint, options, retryCount + 1);
                    }

                    // Redirect to login
                    window.dispatchEvent(new CustomEvent('auth:logout'));
                    throw new APIError('Sitzung abgelaufen. Bitte melden Sie sich erneut an.', response.status, data);
                }

                // Handle rate limiting
                if (response.status === 429) {
                    if (retryCount < this.maxRetries) {
                        const retryAfter = response.headers.get('Retry-After') || this.retryDelay;
                        await this.sleep(parseInt(retryAfter) * 1000);
                        return this.request(endpoint, options, retryCount + 1);
                    }
                }

                throw new APIError(
                    data.detail || data.message || 'Anfrage fehlgeschlagen',
                    response.status,
                    data
                );
            }

            // Apply response interceptors
            const finalResponse = await this.applyResponseInterceptors({
                data,
                status: response.status,
                headers: response.headers
            });

            return finalResponse.data;

        } catch (error) {
            // Handle network errors
            if (error.name === 'AbortError') {
                throw new APIError('Zeitüberschreitung der Anfrage', 408);
            }

            if (error instanceof APIError) {
                throw error;
            }

            // Retry on network error
            if (retryCount < this.maxRetries && !options.skipRetry) {
                await this.sleep(this.retryDelay * (retryCount + 1));
                return this.request(endpoint, options, retryCount + 1);
            }

            throw new APIError(
                'Netzwerkfehler. Bitte überprüfen Sie Ihre Verbindung.',
                0,
                error
            );
        }
    }

    /**
     * Handle token refresh
     */
    async handleTokenRefresh() {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) {
            return false;
        }

        try {
            const response = await this.request('/auth/refresh', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ refresh_token: refreshToken }),
                skipAuth: true,
                skipRetry: true
            });

            // Store new tokens
            localStorage.setItem('access_token', response.access_token);
            localStorage.setItem('refresh_token', response.refresh_token);

            return true;
        } catch (error) {
            // Refresh failed, clear tokens
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            return false;
        }
    }

    /**
     * GET request
     */
    async get(endpoint, config = {}) {
        return this.request(endpoint, {
            ...config,
            method: 'GET'
        });
    }

    /**
     * POST request
     */
    async post(endpoint, data, config = {}) {
        const headers = config.headers || {};

        // Auto-detect content type
        if (!(data instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
        }

        return this.request(endpoint, {
            ...config,
            method: 'POST',
            headers,
            body: data instanceof FormData ? data : JSON.stringify(data)
        });
    }

    /**
     * PUT request
     */
    async put(endpoint, data, config = {}) {
        return this.request(endpoint, {
            ...config,
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                ...config.headers
            },
            body: JSON.stringify(data)
        });
    }

    /**
     * DELETE request
     */
    async delete(endpoint, config = {}) {
        return this.request(endpoint, {
            ...config,
            method: 'DELETE'
        });
    }

    /**
     * Upload file with progress tracking
     */
    async upload(endpoint, file, options = {}) {
        const formData = new FormData();
        formData.append('file', file);

        // Add additional fields
        if (options.fields) {
            Object.entries(options.fields).forEach(([key, value]) => {
                formData.append(key, value);
            });
        }

        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();

            // Progress tracking
            if (options.onProgress) {
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const percentComplete = (e.loaded / e.total) * 100;
                        options.onProgress(percentComplete, e.loaded, e.total);
                    }
                });
            }

            // Success handler
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const data = JSON.parse(xhr.responseText);
                        resolve(data);
                    } catch (error) {
                        resolve(xhr.responseText);
                    }
                } else {
                    try {
                        const error = JSON.parse(xhr.responseText);
                        reject(new APIError(
                            error.detail || 'Upload fehlgeschlagen',
                            xhr.status,
                            error
                        ));
                    } catch {
                        reject(new APIError('Upload fehlgeschlagen', xhr.status));
                    }
                }
            });

            // Error handler
            xhr.addEventListener('error', () => {
                reject(new APIError('Netzwerkfehler beim Upload', 0));
            });

            // Abort handler
            xhr.addEventListener('abort', () => {
                reject(new APIError('Upload abgebrochen', 0));
            });

            // Open connection
            const url = this.buildURL(endpoint, options.includeApiVersion !== false);
            xhr.open('POST', url);

            // Add auth header
            const token = localStorage.getItem('access_token');
            if (token) {
                xhr.setRequestHeader('Authorization', `Bearer ${token}`);
            }

            // Send request
            xhr.send(formData);

            // Store xhr for potential cancellation
            if (options.onXHR) {
                options.onXHR(xhr);
            }
        });
    }
}

/**
 * Custom API Error class
 */
class APIError extends Error {
    constructor(message, status, data = null) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.data = data;
    }
}

// Create singleton instance
const api = new APIClient();

// Export API instance and error class
window.api = api;
window.APIError = APIError;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { api, APIError, APIClient };
}
