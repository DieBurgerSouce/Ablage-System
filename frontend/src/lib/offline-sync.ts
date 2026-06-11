/**
 * Offline Sync Utilities
 *
 * Provides synchronization between offline storage and server.
 *
 * Features:
 * - Mutation queue processing
 * - Conflict resolution
 * - Retry with backoff
 * - Sync status events
 *
 * Phase 3.1 der Feature-Roadmap (Januar 2026)
 */

import {
  getDB,
  getPendingMutations,
  updateMutationStatus,
  removeMutation,
  type OfflineMutation,
} from './storage/indexed-db';
import { logger } from './logger';

// ==================== Types ====================

export type SyncStatus = 'idle' | 'syncing' | 'error' | 'complete';

export interface SyncResult {
  success: boolean;
  processed: number;
  failed: number;
  remaining: number;
  errors: Array<{ id: string; error: string }>;
}

export interface SyncOptions {
  /** Maximum number of mutations to process per sync */
  batchSize?: number;
  /** Maximum retry attempts per mutation */
  maxRetries?: number;
  /** Base delay for exponential backoff (ms) */
  baseDelay?: number;
  /** Whether to stop on first error */
  stopOnError?: boolean;
}

// ==================== Event Emitter ====================

type SyncEventType = 'sync-start' | 'sync-progress' | 'sync-complete' | 'sync-error';

interface SyncEvent {
  type: SyncEventType;
  data: {
    processed?: number;
    total?: number;
    mutation?: OfflineMutation;
    error?: string;
    result?: SyncResult;
  };
}

const syncListeners: Map<SyncEventType, Set<(event: SyncEvent) => void>> = new Map();

export function addSyncListener(
  type: SyncEventType,
  callback: (event: SyncEvent) => void
): () => void {
  if (!syncListeners.has(type)) {
    syncListeners.set(type, new Set());
  }
  syncListeners.get(type)!.add(callback);

  return () => {
    syncListeners.get(type)?.delete(callback);
  };
}

function emitSyncEvent(event: SyncEvent): void {
  syncListeners.get(event.type)?.forEach((callback) => {
    try {
      callback(event);
    } catch (error) {
      logger.error('[OfflineSync] Event callback error', { error });
    }
  });
}

// ==================== Sync State ====================

let currentSyncStatus: SyncStatus = 'idle';
let syncInProgress = false;

export function getSyncStatus(): SyncStatus {
  return currentSyncStatus;
}

export function isSyncing(): boolean {
  return syncInProgress;
}

// ==================== Sync Implementation ====================

const DEFAULT_OPTIONS: Required<SyncOptions> = {
  batchSize: 10,
  maxRetries: 3,
  baseDelay: 1000,
  stopOnError: false,
};

/**
 * Calculate exponential backoff delay
 */
function getBackoffDelay(attempt: number, baseDelay: number): number {
  return Math.min(baseDelay * Math.pow(2, attempt), 30000);
}

/**
 * Sleep for specified milliseconds
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Process a single mutation
 */
async function processMutation(
  mutation: OfflineMutation,
  options: Required<SyncOptions>
): Promise<boolean> {
  try {
    await updateMutationStatus(mutation.id, 'processing');

    const response = await fetch(mutation.endpoint, {
      method: mutation.method,
      headers: {
        'Content-Type': 'application/json',
      },
      body: mutation.payload ? JSON.stringify(mutation.payload) : undefined,
      credentials: 'include',
    });

    if (response.ok) {
      await removeMutation(mutation.id);
      logger.info('[OfflineSync] Mutation synced', { id: mutation.id });
      return true;
    }

    // Handle specific error codes
    if (response.status === 409) {
      // Conflict - data was already processed or is stale
      await removeMutation(mutation.id);
      logger.warn('[OfflineSync] Conflict - mutation removed', { id: mutation.id });
      return true;
    }

    if (response.status >= 400 && response.status < 500) {
      // Client error - don't retry
      await updateMutationStatus(
        mutation.id,
        'failed',
        `HTTP ${response.status}: ${response.statusText}`
      );
      return false;
    }

    // Server error - mark for retry
    const errorMsg = `HTTP ${response.status}`;
    if (mutation.retryCount >= options.maxRetries) {
      await updateMutationStatus(mutation.id, 'failed', errorMsg);
      return false;
    }

    await updateMutationStatus(mutation.id, 'pending', errorMsg);
    return false;
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Unknown error';

    if (mutation.retryCount >= options.maxRetries) {
      await updateMutationStatus(mutation.id, 'failed', errorMsg);
      return false;
    }

    await updateMutationStatus(mutation.id, 'pending', errorMsg);
    return false;
  }
}

/**
 * Sync all pending mutations
 */
export async function syncOfflineMutations(
  options: SyncOptions = {}
): Promise<SyncResult> {
  if (syncInProgress) {
    logger.warn('[OfflineSync] Sync already in progress');
    return {
      success: false,
      processed: 0,
      failed: 0,
      remaining: 0,
      errors: [{ id: '', error: 'Sync already in progress' }],
    };
  }

  if (!navigator.onLine) {
    logger.warn('[OfflineSync] Cannot sync while offline');
    return {
      success: false,
      processed: 0,
      failed: 0,
      remaining: 0,
      errors: [{ id: '', error: 'Offline' }],
    };
  }

  const opts = { ...DEFAULT_OPTIONS, ...options };
  syncInProgress = true;
  currentSyncStatus = 'syncing';

  const result: SyncResult = {
    success: true,
    processed: 0,
    failed: 0,
    remaining: 0,
    errors: [],
  };

  try {
    emitSyncEvent({ type: 'sync-start', data: {} });
    logger.info('[OfflineSync] Starting sync');

    const mutations = await getPendingMutations();
    const toProcess = mutations.slice(0, opts.batchSize);

    logger.info('[OfflineSync] Processing mutations', {
      total: mutations.length,
      batch: toProcess.length,
    });

    for (let i = 0; i < toProcess.length; i++) {
      const mutation = toProcess[i];

      // Add backoff delay for retries
      if (mutation.retryCount > 0) {
        const delay = getBackoffDelay(mutation.retryCount, opts.baseDelay);
        await sleep(delay);
      }

      emitSyncEvent({
        type: 'sync-progress',
        data: {
          processed: i,
          total: toProcess.length,
          mutation,
        },
      });

      const success = await processMutation(mutation, opts);

      if (success) {
        result.processed++;
      } else {
        result.failed++;
        result.errors.push({
          id: mutation.id,
          error: mutation.errorMessage || 'Unknown error',
        });

        if (opts.stopOnError) {
          break;
        }
      }
    }

    // Get remaining count
    const remaining = await getPendingMutations();
    result.remaining = remaining.length;
    result.success = result.failed === 0;

    currentSyncStatus = result.success ? 'complete' : 'error';

    emitSyncEvent({
      type: 'sync-complete',
      data: { result },
    });

    logger.info('[OfflineSync] Sync complete', result);
  } catch (error) {
    currentSyncStatus = 'error';
    result.success = false;
    result.errors.push({
      id: '',
      error: error instanceof Error ? error.message : 'Unknown error',
    });

    emitSyncEvent({
      type: 'sync-error',
      data: { error: result.errors[result.errors.length - 1].error },
    });

    logger.error('[OfflineSync] Sync failed', { error });
  } finally {
    syncInProgress = false;
  }

  return result;
}

/**
 * Request background sync from Service Worker
 */
export async function requestBackgroundSync(): Promise<boolean> {
  if (!('serviceWorker' in navigator)) {
    return false;
  }

  try {
    const registration = await navigator.serviceWorker.ready;

    if ('sync' in registration) {
      // Background-Sync-API fehlt in den DOM-Lib-Typen (extern erzwungener Cast)
      await (registration as unknown as { sync: { register: (tag: string) => Promise<void> } }).sync.register('offline-mutations');
      logger.info('[OfflineSync] Background sync registered');
      return true;
    }

    // Fallback: trigger sync via message
    registration.active?.postMessage({ type: 'TRIGGER_SYNC' });
    return true;
  } catch (error) {
    logger.error('[OfflineSync] Background sync registration failed', { error });
    return false;
  }
}

/**
 * Clear failed mutations
 */
export async function clearFailedMutations(): Promise<number> {
  try {
    const db = await getDB();
    const all = await db.getAll('mutations');
    const failed = all.filter((m) => m.status === 'failed');

    for (const mutation of failed) {
      await removeMutation(mutation.id);
    }

    logger.info('[OfflineSync] Cleared failed mutations', { count: failed.length });
    return failed.length;
  } catch (error) {
    logger.error('[OfflineSync] Failed to clear mutations', { error });
    return 0;
  }
}

/**
 * Auto-sync when coming online
 */
export function enableAutoSync(): () => void {
  const handleOnline = () => {
    logger.info('[OfflineSync] Back online - triggering sync');
    // Small delay to ensure network is stable
    setTimeout(() => {
      syncOfflineMutations();
    }, 2000);
  };

  window.addEventListener('online', handleOnline);

  return () => {
    window.removeEventListener('online', handleOnline);
  };
}

// ==================== Exports ====================

export type { OfflineMutation };
