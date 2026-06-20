/**
 * Offline API Wrapper
 *
 * Wraps API calls to support offline mode:
 * - Queues mutations when offline
 * - Returns cached data when available
 * - Provides optimistic updates
 *
 * @module offline-api-wrapper
 */

import {
  addMutation,
  cacheDocument,
  getCachedDocument,
  getAllCachedDocuments,
  type CachedDocument,
} from '@/lib/storage/indexed-db';
import { apiClient } from '@/lib/api/client';
import { logger } from '@/lib/logger';

// ============================================
// Types
// ============================================

export interface OfflineApiOptions {
  /** Cache response for offline use (default: true for GET) */
  cacheResponse?: boolean;
  /** Cache TTL in milliseconds (default: 7 days) */
  cacheTtlMs?: number;
  /** Queue if offline (default: true for mutations) */
  queueIfOffline?: boolean;
  /** Max retries for queued mutations (default: 3) */
  maxRetries?: number;
  /** Return cached data when offline (default: true) */
  returnCachedWhenOffline?: boolean;
}

export interface OfflineApiResult<T> {
  data: T | null;
  fromCache: boolean;
  queued: boolean;
  error?: string;
}

// ============================================
// Utility Functions
// ============================================

/**
 * Check if we're currently online
 */
export function isOnline(): boolean {
  return typeof navigator !== 'undefined' ? navigator.onLine : true;
}


// ============================================
// Offline API Functions
// ============================================

/**
 * Make an API request with offline support
 */
export async function offlineRequest<T>(
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  endpoint: string,
  data?: unknown,
  options: OfflineApiOptions = {}
): Promise<OfflineApiResult<T>> {
  const {
    cacheResponse = method === 'GET',
    cacheTtlMs = 7 * 24 * 60 * 60 * 1000, // 7 days
    queueIfOffline = method !== 'GET',
    maxRetries = 3,
    returnCachedWhenOffline = true,
  } = options;

  // Check online status
  const online = isOnline();

  // If online, make the request
  if (online) {
    try {
      const response = await apiClient.request<T>({
        method,
        url: endpoint,
        data: method !== 'GET' ? data : undefined,
        params: method === 'GET' ? data : undefined,
      });

      // Cache GET responses if enabled
      if (cacheResponse && method === 'GET' && response.data) {
        // For document endpoints, cache in IndexedDB
        if (endpoint.includes('/documents/') && typeof response.data === 'object') {
          const doc = response.data as Record<string, unknown>;
          if (doc.id && typeof doc.id === 'string') {
            await cacheDocument(
              {
                id: doc.id,
                title: (doc.title as string) || (doc.filename as string) || 'Unbenannt',
                content: (doc.content as string) || '',
                extractedText: (doc.extracted_text as string) || (doc.ocr_text as string),
                metadata: (doc.metadata as Record<string, unknown>) || {},
                thumbnailUrl: doc.thumbnail_url as string | undefined,
              },
              cacheTtlMs
            );
          }
        }
      }

      return {
        data: response.data,
        fromCache: false,
        queued: false,
      };
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Unbekannter Fehler';
      logger.error('[OfflineAPI] Request fehlgeschlagen', {
        endpoint,
        error: errorMessage,
      });

      return {
        data: null,
        fromCache: false,
        queued: false,
        error: errorMessage,
      };
    }
  }

  // Offline handling
  logger.info('[OfflineAPI] Offline - verwende Fallback', { endpoint, method });

  // For GET requests, try to return cached data
  if (method === 'GET' && returnCachedWhenOffline) {
    // Try to get cached document
    if (endpoint.includes('/documents/')) {
      const docIdMatch = endpoint.match(/\/documents\/([a-f0-9-]+)/i);
      if (docIdMatch) {
        const cachedDoc = await getCachedDocument(docIdMatch[1]);
        if (cachedDoc) {
          logger.info('[OfflineAPI] Dokument aus Cache geladen', {
            id: cachedDoc.id,
          });
          return {
            data: cachedDoc as unknown as T,
            fromCache: true,
            queued: false,
          };
        }
      }
    }

    return {
      data: null,
      fromCache: false,
      queued: false,
      error: 'Offline - keine gecachten Daten verfügbar',
    };
  }

  // For mutations, queue them
  if (queueIfOffline && method !== 'GET') {
    const mutationId = await addMutation({
      endpoint,
      method,
      payload: data,
      maxRetries,
    });

    logger.info('[OfflineAPI] Mutation in Queue gespeichert', {
      id: mutationId,
      endpoint,
    });

    return {
      data: null,
      fromCache: false,
      queued: true,
    };
  }

  return {
    data: null,
    fromCache: false,
    queued: false,
    error: 'Offline - Aktion nicht möglich',
  };
}

// ============================================
// Convenience Functions
// ============================================

/**
 * GET request with offline support
 */
export async function offlineGet<T>(
  endpoint: string,
  params?: Record<string, unknown>,
  options?: OfflineApiOptions
): Promise<OfflineApiResult<T>> {
  return offlineRequest<T>('GET', endpoint, params, options);
}

/**
 * POST request with offline support (queued when offline)
 */
export async function offlinePost<T>(
  endpoint: string,
  data?: unknown,
  options?: OfflineApiOptions
): Promise<OfflineApiResult<T>> {
  return offlineRequest<T>('POST', endpoint, data, options);
}

/**
 * PUT request with offline support (queued when offline)
 */
export async function offlinePut<T>(
  endpoint: string,
  data?: unknown,
  options?: OfflineApiOptions
): Promise<OfflineApiResult<T>> {
  return offlineRequest<T>('PUT', endpoint, data, options);
}

/**
 * PATCH request with offline support (queued when offline)
 */
export async function offlinePatch<T>(
  endpoint: string,
  data?: unknown,
  options?: OfflineApiOptions
): Promise<OfflineApiResult<T>> {
  return offlineRequest<T>('PATCH', endpoint, data, options);
}

/**
 * DELETE request with offline support (queued when offline)
 */
export async function offlineDelete<T>(
  endpoint: string,
  data?: unknown,
  options?: OfflineApiOptions
): Promise<OfflineApiResult<T>> {
  return offlineRequest<T>('DELETE', endpoint, data, options);
}

// ============================================
// Document-specific Functions
// ============================================

/**
 * Get all cached documents for offline browsing
 */
export async function getOfflineDocuments(): Promise<CachedDocument[]> {
  return getAllCachedDocuments();
}

/**
 * Get a specific document (online or cached)
 */
export async function getDocument(
  documentId: string
): Promise<OfflineApiResult<CachedDocument>> {
  return offlineGet<CachedDocument>(`/documents/${documentId}`);
}

/**
 * Cache multiple documents for offline use
 */
export async function cacheDocumentsForOffline(
  documentIds: string[]
): Promise<number> {
  let cached = 0;

  for (const id of documentIds) {
    try {
      const result = await offlineGet(`/documents/${id}`);
      if (result.data && !result.fromCache) {
        cached++;
      }
    } catch (error) {
      logger.error('[OfflineAPI] Dokument konnte nicht gecached werden', {
        id,
        error,
      });
    }
  }

  return cached;
}
