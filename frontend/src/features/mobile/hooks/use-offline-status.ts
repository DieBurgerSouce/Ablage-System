/**
 * useOfflineStatus Hook
 *
 * Monitors online/offline status and provides offline-related utilities.
 *
 * Features:
 * - Network status monitoring
 * - Connection quality detection
 * - Pending sync count
 * - Service Worker status
 *
 * Phase 3.1 der Feature-Roadmap (Januar 2026)
 */

import { useState, useEffect, useCallback } from 'react';
import { logger } from '@/lib/logger';
import { getPendingMutationCount, getStorageEstimate } from '@/lib/storage/indexed-db';

// ==================== Types ====================

export type ConnectionType = 'online' | 'offline' | 'slow';

export interface NetworkInfo {
  isOnline: boolean;
  connectionType: ConnectionType;
  effectiveType?: '4g' | '3g' | '2g' | 'slow-2g';
  downlink?: number;
  rtt?: number;
  saveData?: boolean;
}

export interface StorageInfo {
  usage: number;
  quota: number;
  percentUsed: number;
}

export interface ServiceWorkerInfo {
  isRegistered: boolean;
  isActive: boolean;
  updateAvailable: boolean;
  version?: string;
}

interface UseOfflineStatusReturn {
  // Network
  networkInfo: NetworkInfo;
  isOnline: boolean;
  connectionType: ConnectionType;

  // Sync
  pendingSyncCount: number;
  hasPendingSync: boolean;

  // Storage
  storageInfo: StorageInfo | null;
  isStorageLow: boolean;

  // Service Worker
  swInfo: ServiceWorkerInfo;

  // Actions
  refreshStatus: () => Promise<void>;
  triggerSync: () => Promise<void>;
  checkForUpdates: () => Promise<void>;
}

// ==================== Helpers ====================

interface NetworkConnection {
  effectiveType?: '4g' | '3g' | '2g' | 'slow-2g';
  downlink?: number;
  rtt?: number;
  saveData?: boolean;
  addEventListener: (type: string, listener: EventListener) => void;
  removeEventListener: (type: string, listener: EventListener) => void;
}

function getNavigatorConnection(): NetworkConnection | undefined {
  return (navigator as unknown as { connection?: NetworkConnection }).connection ||
    (navigator as unknown as { mozConnection?: NetworkConnection }).mozConnection ||
    (navigator as unknown as { webkitConnection?: NetworkConnection }).webkitConnection;
}

function getNetworkInfo(): NetworkInfo {
  const connection = getNavigatorConnection();

  const isOnline = navigator.onLine;
  let connectionType: ConnectionType = isOnline ? 'online' : 'offline';

  // Check for slow connection
  if (isOnline && connection) {
    if (
      connection.effectiveType === '2g' ||
      connection.effectiveType === 'slow-2g' ||
      (connection.rtt && connection.rtt > 500) ||
      (connection.downlink && connection.downlink < 0.5)
    ) {
      connectionType = 'slow';
    }
  }

  return {
    isOnline,
    connectionType,
    effectiveType: connection?.effectiveType,
    downlink: connection?.downlink,
    rtt: connection?.rtt,
    saveData: connection?.saveData,
  };
}

// ==================== Hook ====================

export function useOfflineStatus(): UseOfflineStatusReturn {
  const [networkInfo, setNetworkInfo] = useState<NetworkInfo>(getNetworkInfo);
  const [pendingSyncCount, setPendingSyncCount] = useState(0);
  const [storageInfo, setStorageInfo] = useState<StorageInfo | null>(null);
  const [swInfo, setSwInfo] = useState<ServiceWorkerInfo>({
    isRegistered: false,
    isActive: false,
    updateAvailable: false,
  });

  // ==================== Network Monitoring ====================

  useEffect(() => {
    const updateNetworkInfo = () => {
      const info = getNetworkInfo();
      setNetworkInfo(info);
      logger.info('[useOfflineStatus] Network status changed', info);
    };

    window.addEventListener('online', updateNetworkInfo);
    window.addEventListener('offline', updateNetworkInfo);

    // Listen for connection changes
    const connection = getNavigatorConnection();
    if (connection) {
      connection.addEventListener('change', updateNetworkInfo);
    }

    return () => {
      window.removeEventListener('online', updateNetworkInfo);
      window.removeEventListener('offline', updateNetworkInfo);
      if (connection) {
        connection.removeEventListener('change', updateNetworkInfo);
      }
    };
  }, []);

  // ==================== Sync Count ====================

  const refreshPendingSync = useCallback(async () => {
    try {
      const count = await getPendingMutationCount();
      setPendingSyncCount(count);
    } catch (error) {
      logger.error('[useOfflineStatus] Failed to get pending sync count', { error });
    }
  }, []);

  useEffect(() => {
    // Initial load + periodic refresh
    let cancelled = false;
    const doRefresh = async () => {
      if (!cancelled) {
        try {
          const count = await getPendingMutationCount();
          if (!cancelled) setPendingSyncCount(count);
        } catch (error) {
          logger.error('[useOfflineStatus] Failed to get pending sync count', { error });
        }
      }
    };
    doRefresh();

    const interval = setInterval(doRefresh, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // ==================== Storage Info ====================

  const refreshStorageInfo = useCallback(async () => {
    try {
      const info = await getStorageEstimate();
      setStorageInfo(info);
    } catch (error) {
      logger.error('[useOfflineStatus] Failed to get storage estimate', { error });
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const doRefresh = async () => {
      if (!cancelled) {
        try {
          const info = await getStorageEstimate();
          if (!cancelled) setStorageInfo(info);
        } catch (error) {
          logger.error('[useOfflineStatus] Failed to get storage estimate', { error });
        }
      }
    };
    doRefresh();
    return () => { cancelled = true; };
  }, []);

  // ==================== Service Worker ====================

  useEffect(() => {
    if (!('serviceWorker' in navigator)) {
      return;
    }

    const checkServiceWorker = async () => {
      try {
        const registration = await navigator.serviceWorker.getRegistration();

        if (registration) {
          const info: ServiceWorkerInfo = {
            isRegistered: true,
            isActive: !!registration.active,
            updateAvailable: !!registration.waiting,
          };
          setSwInfo(info);

          // Listen for updates
          registration.addEventListener('updatefound', () => {
            setSwInfo((prev) => ({ ...prev, updateAvailable: true }));
          });
        }
      } catch (error) {
        logger.error('[useOfflineStatus] Failed to check service worker', { error });
      }
    };

    checkServiceWorker();
  }, []);

  // ==================== Actions ====================

  const refreshStatus = useCallback(async () => {
    setNetworkInfo(getNetworkInfo());
    await refreshPendingSync();
    await refreshStorageInfo();
  }, [refreshPendingSync, refreshStorageInfo]);

  const triggerSync = useCallback(async () => {
    if (!('serviceWorker' in navigator)) return;

    try {
      const registration = await navigator.serviceWorker.ready;

      // Try Background Sync API
      if ('sync' in registration) {
        await (registration as unknown as { sync: { register: (tag: string) => Promise<void> } }).sync.register('offline-mutations');
        logger.info('[useOfflineStatus] Background sync triggered');
      } else {
        // Fallback: send message to SW
        registration.active?.postMessage({ type: 'TRIGGER_SYNC' });
      }

      // Refresh count after short delay
      setTimeout(refreshPendingSync, 2000);
    } catch (error) {
      logger.error('[useOfflineStatus] Failed to trigger sync', { error });
    }
  }, [refreshPendingSync]);

  const checkForUpdates = useCallback(async () => {
    if (!('serviceWorker' in navigator)) return;

    try {
      const registration = await navigator.serviceWorker.getRegistration();
      if (registration) {
        await registration.update();
        logger.info('[useOfflineStatus] Checked for SW updates');
      }
    } catch (error) {
      logger.error('[useOfflineStatus] Failed to check for updates', { error });
    }
  }, []);

  // ==================== Computed ====================

  const isStorageLow = storageInfo ? storageInfo.percentUsed > 90 : false;

  return {
    networkInfo,
    isOnline: networkInfo.isOnline,
    connectionType: networkInfo.connectionType,
    pendingSyncCount,
    hasPendingSync: pendingSyncCount > 0,
    storageInfo,
    isStorageLow,
    swInfo,
    refreshStatus,
    triggerSync,
    checkForUpdates,
  };
}

export default useOfflineStatus;
