/**
 * API Client Index
 *
 * Central export point for API utilities.
 * Re-exports the axios-based apiClient and provides a fetch-like wrapper.
 */

import { apiClient } from './client';
import type { AxiosRequestConfig } from 'axios';

// Re-export the axios client
export { apiClient };

// Alias for backwards compatibility - many files import { api } from '@/lib/api'
export { apiClient as api };

// Re-export error handling utility
export { handleApiError } from './error-toast-handler';

// Re-export query client
export { queryClient } from './query-client';

// Re-export error handling
export { showApiErrorToast } from './error-toast-handler';

/**
 * Fetch-like wrapper around axios apiClient for simpler API calls.
 *
 * This provides a cleaner interface for simple GET/POST requests while
 * still using the authenticated axios instance with interceptors.
 *
 * WICHTIG: URLs sind RELATIV zur apiClient-baseURL ('/api/v1').
 * NIEMALS '/api/v1/...' uebergeben — das ergibt '/api/v1/api/v1/...' (404).
 *
 * @example
 * // Simple GET request
 * const data = await fetchWithAuth<User[]>('/users');
 *
 * @example
 * // POST request with body
 * const result = await fetchWithAuth<CreateResponse>('/items', {
 *   method: 'POST',
 *   body: JSON.stringify({ name: 'Item' }),
 * });
 */
export async function fetchWithAuth<T>(
  url: string,
  options?: {
    method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    body?: string;
    headers?: Record<string, string>;
  }
): Promise<T> {
  const config: AxiosRequestConfig = {
    url,
    method: options?.method || 'GET',
    headers: options?.headers,
  };

  // Parse body if provided (axios uses 'data' instead of 'body')
  if (options?.body) {
    try {
      config.data = JSON.parse(options.body);
    } catch {
      config.data = options.body;
    }
  }

  const response = await apiClient.request<T>(config);
  return response.data;
}
