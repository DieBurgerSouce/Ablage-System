/**
 * useOfflineSync Hook
 *
 * React hook for managing offline synchronization state.
 * Provides:
 * - Sync progress tracking
 * - Manual sync trigger
 * - Pending mutation count
 * - Auto-sync setup
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { syncService, type SyncProgress, type SyncResult, type SyncEventDetail } from './sync-service';
import { getPendingMutationCount } from '@/lib/storage/indexed-db';
import { useOnlineStatus } from '@/lib/hooks/use-online-status';

export interface UseOfflineSyncOptions {
  /** Enable auto-sync when coming back online (default: true) */
  autoSync?: boolean;
  /** Auto-sync on mount if pending mutations exist (default: true) */
  syncOnMount?: boolean;
  /** Callback when sync starts */
  onSyncStart?: () => void;
  /** Callback when sync completes */
  onSyncComplete?: (result: SyncResult) => void;
  /** Callback when sync fails */
  onSyncError?: (error: string) => void;
}

export interface UseOfflineSyncResult {
  /** Current sync progress */
  progress: SyncProgress;
  /** Number of pending mutations */
  pendingCount: number;
  /** Whether sync is in progress */
  isSyncing: boolean;
  /** Online status */
  isOnline: boolean;
  /** Manually trigger sync */
  sync: () => Promise<SyncResult>;
  /** Refresh pending count */
  refreshPendingCount: () => Promise<void>;
}

export function useOfflineSync(options: UseOfflineSyncOptions = {}): UseOfflineSyncResult {
  const {
    autoSync = true,
    syncOnMount = true,
    onSyncStart,
    onSyncComplete,
    onSyncError,
  } = options;

  const [progress, setProgress] = useState<SyncProgress>(() => syncService.getProgress());
  const [pendingCount, setPendingCount] = useState(0);
  const cleanupRef = useRef<(() => void) | null>(null);
  const mountedRef = useRef(true);

  const { isOnline, isConnected } = useOnlineStatus({
    pingVerification: false,
  });

  /**
   * Refresh pending mutation count
   */
  const refreshPendingCount = useCallback(async () => {
    const count = await getPendingMutationCount();
    if (mountedRef.current) {
      setPendingCount(count);
    }
  }, []);

  /**
   * Trigger manual sync
   */
  const sync = useCallback(async (): Promise<SyncResult> => {
    if (!isOnline) {
      return {
        success: false,
        total: 0,
        succeeded: 0,
        failed: 0,
        errors: [{ mutationId: '', error: 'Offline - Sync nicht moeglich' }],
      };
    }

    onSyncStart?.();
    const result = await syncService.sync();

    if (result.success) {
      onSyncComplete?.(result);
    } else if (result.errors.length > 0) {
      onSyncError?.(result.errors[0].error);
    }

    await refreshPendingCount();
    return result;
  }, [isOnline, onSyncStart, onSyncComplete, onSyncError, refreshPendingCount]);

  /**
   * Handle sync events
   */
  useEffect(() => {
    const handleSyncEvent = (event: CustomEvent<SyncEventDetail>) => {
      if (!mountedRef.current) return;

      setProgress(event.detail.progress);

      if (event.detail.type === 'complete' && event.detail.result) {
        refreshPendingCount();
      }
    };

    window.addEventListener('offline-sync', handleSyncEvent as EventListener);

    return () => {
      window.removeEventListener('offline-sync', handleSyncEvent as EventListener);
    };
  }, [refreshPendingCount]);

  /**
   * Setup auto-sync when coming back online
   */
  useEffect(() => {
    if (autoSync) {
      cleanupRef.current = syncService.setupAutoSync();
    }

    return () => {
      cleanupRef.current?.();
    };
  }, [autoSync]);

  /**
   * Sync on mount if enabled and pending mutations exist
   */
  useEffect(() => {
    const initSync = async () => {
      await refreshPendingCount();

      if (syncOnMount && isOnline) {
        const count = await getPendingMutationCount();
        if (count > 0) {
          await sync();
        }
      }
    };

    initSync();

    return () => {
      mountedRef.current = false;
    };
  }, []); // Only on mount

  return {
    progress,
    pendingCount,
    isSyncing: syncService.isSyncInProgress(),
    isOnline,
    sync,
    refreshPendingCount,
  };
}

export default useOfflineSync;
