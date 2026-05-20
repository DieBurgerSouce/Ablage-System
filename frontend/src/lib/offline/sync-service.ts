/**
 * Offline Sync Service
 *
 * Enterprise-grade synchronization service for offline mutations.
 * Handles:
 * - Processing queued mutations when back online
 * - Conflict resolution
 * - Background sync registration
 * - Progress tracking with events
 *
 * @module sync-service
 */

import {
  getPendingMutations,
  updateMutationStatus,
  removeMutation,
  type OfflineMutation,
  getPendingMutationCount,
} from '@/lib/storage/indexed-db';
import { apiClient } from '@/lib/api/client';
import { logger } from '@/lib/logger';

// ============================================
// Types
// ============================================

export interface SyncProgress {
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  currentMutation: OfflineMutation | null;
  status: 'idle' | 'syncing' | 'completed' | 'error';
}

export interface SyncResult {
  success: boolean;
  total: number;
  succeeded: number;
  failed: number;
  errors: Array<{ mutationId: string; error: string }>;
}

export interface SyncEventDetail {
  type: 'start' | 'progress' | 'complete' | 'error';
  progress: SyncProgress;
  result?: SyncResult;
}

// ============================================
// Sync Service
// ============================================

class OfflineSyncService {
  private isSyncing = false;
  private progress: SyncProgress = {
    total: 0,
    processed: 0,
    succeeded: 0,
    failed: 0,
    currentMutation: null,
    status: 'idle',
  };

  /**
   * Get current sync progress
   */
  getProgress(): SyncProgress {
    return { ...this.progress };
  }

  /**
   * Check if sync is in progress
   */
  isSyncInProgress(): boolean {
    return this.isSyncing;
  }

  /**
   * Get count of pending mutations
   */
  async getPendingCount(): Promise<number> {
    return getPendingMutationCount();
  }

  /**
   * Dispatch sync event to window
   */
  private dispatchSyncEvent(detail: SyncEventDetail): void {
    window.dispatchEvent(
      new CustomEvent<SyncEventDetail>('offline-sync', { detail })
    );
  }

  /**
   * Process a single mutation
   */
  private async processMutation(mutation: OfflineMutation): Promise<boolean> {
    try {
      await updateMutationStatus(mutation.id, 'processing');

      // Make the API call
      const response = await apiClient.request({
        url: mutation.endpoint,
        method: mutation.method,
        data: mutation.method !== 'GET' ? mutation.payload : undefined,
        params: mutation.method === 'GET' ? mutation.payload : undefined,
        timeout: 30000, // Longer timeout for sync
      });

      // Success - remove from queue
      if (response.status >= 200 && response.status < 300) {
        await removeMutation(mutation.id);
        logger.info('[SyncService] Mutation erfolgreich synchronisiert', {
          id: mutation.id,
          endpoint: mutation.endpoint,
        });
        return true;
      }

      // Unexpected status - mark as failed
      await updateMutationStatus(
        mutation.id,
        'failed',
        `Unerwarteter Status: ${response.status}`
      );
      return false;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Unbekannter Fehler';

      // Check if max retries reached
      if (mutation.retryCount >= mutation.maxRetries) {
        await updateMutationStatus(mutation.id, 'failed', errorMessage);
        logger.error('[SyncService] Mutation endgültig fehlgeschlagen', {
          id: mutation.id,
          error: errorMessage,
        });
        return false;
      }

      // Keep as pending for next sync attempt
      await updateMutationStatus(mutation.id, 'pending', errorMessage);
      logger.warn('[SyncService] Mutation wird erneut versucht', {
        id: mutation.id,
        retryCount: mutation.retryCount + 1,
        error: errorMessage,
      });
      return false;
    }
  }

  /**
   * Sync all pending mutations
   */
  async sync(): Promise<SyncResult> {
    if (this.isSyncing) {
      logger.warn('[SyncService] Synchronisierung läuft bereits');
      return {
        success: false,
        total: 0,
        succeeded: 0,
        failed: 0,
        errors: [{ mutationId: '', error: 'Sync bereits aktiv' }],
      };
    }

    this.isSyncing = true;
    const errors: Array<{ mutationId: string; error: string }> = [];

    try {
      const mutations = await getPendingMutations();

      this.progress = {
        total: mutations.length,
        processed: 0,
        succeeded: 0,
        failed: 0,
        currentMutation: null,
        status: 'syncing',
      };

      // Dispatch start event
      this.dispatchSyncEvent({ type: 'start', progress: this.progress });

      if (mutations.length === 0) {
        this.progress.status = 'completed';
        this.dispatchSyncEvent({
          type: 'complete',
          progress: this.progress,
          result: { success: true, total: 0, succeeded: 0, failed: 0, errors: [] },
        });
        return { success: true, total: 0, succeeded: 0, failed: 0, errors: [] };
      }

      logger.info('[SyncService] Starte Synchronisierung', {
        count: mutations.length,
      });

      // Process mutations sequentially to maintain order
      for (const mutation of mutations) {
        this.progress.currentMutation = mutation;
        this.dispatchSyncEvent({ type: 'progress', progress: this.progress });

        const success = await this.processMutation(mutation);

        this.progress.processed += 1;
        if (success) {
          this.progress.succeeded += 1;
        } else {
          this.progress.failed += 1;
          errors.push({
            mutationId: mutation.id,
            error: mutation.errorMessage || 'Unbekannter Fehler',
          });
        }

        this.dispatchSyncEvent({ type: 'progress', progress: this.progress });
      }

      this.progress.status = 'completed';
      this.progress.currentMutation = null;

      const result: SyncResult = {
        success: this.progress.failed === 0,
        total: this.progress.total,
        succeeded: this.progress.succeeded,
        failed: this.progress.failed,
        errors,
      };

      this.dispatchSyncEvent({ type: 'complete', progress: this.progress, result });

      logger.info('[SyncService] Synchronisierung abgeschlossen', result);

      return result;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Unbekannter Fehler';
      this.progress.status = 'error';

      this.dispatchSyncEvent({
        type: 'error',
        progress: this.progress,
      });

      logger.error('[SyncService] Synchronisierung fehlgeschlagen', {
        error: errorMessage,
      });

      return {
        success: false,
        total: this.progress.total,
        succeeded: this.progress.succeeded,
        failed: this.progress.failed,
        errors: [{ mutationId: '', error: errorMessage }],
      };
    } finally {
      this.isSyncing = false;
    }
  }

  /**
   * Register for background sync (if supported)
   */
  async registerBackgroundSync(): Promise<boolean> {
    if (!('serviceWorker' in navigator)) {
      logger.warn('[SyncService] Service Worker nicht unterstützt');
      return false;
    }

    try {
      const registration = await navigator.serviceWorker.ready;

      // Check if Background Sync API is available
      if ('sync' in registration) {
        await (registration as any).sync.register('offline-mutations');
        logger.info('[SyncService] Background Sync registriert');
        return true;
      }

      logger.warn('[SyncService] Background Sync API nicht unterstützt');
      return false;
    } catch (error) {
      logger.error('[SyncService] Background Sync Registrierung fehlgeschlagen', {
        error,
      });
      return false;
    }
  }

  /**
   * Auto-sync when coming back online
   */
  setupAutoSync(): () => void {
    const handleOnline = async () => {
      logger.info('[SyncService] Online erkannt - starte Auto-Sync');
      const pendingCount = await this.getPendingCount();
      if (pendingCount > 0) {
        await this.sync();
      }
    };

    window.addEventListener('online', handleOnline);

    // Also try background sync
    this.registerBackgroundSync();

    // Return cleanup function
    return () => {
      window.removeEventListener('online', handleOnline);
    };
  }
}

// Singleton instance
export const syncService = new OfflineSyncService();

// Export for direct import
export default syncService;
