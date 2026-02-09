/**
 * useCameraScan Hook
 *
 * Provides camera scanning state management with offline support.
 *
 * Features:
 * - Camera permission handling
 * - Captured images queue
 * - Offline upload queue
 * - Background sync status
 *
 * Phase 3.1 der Feature-Roadmap (Januar 2026)
 */

import { useState, useCallback, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import {
  addMutation,
  getPendingMutationCount,
  getPendingMutations,
  removeMutation,
} from '@/lib/storage/indexed-db';

// ==================== Types ====================

export interface CapturedDocument {
  id: string;
  dataUrl: string;
  blob: Blob;
  timestamp: number;
  status: 'pending' | 'uploading' | 'uploaded' | 'failed';
  folderId?: string;
  errorMessage?: string;
}

interface UseCameraScanReturn {
  // State
  capturedDocuments: CapturedDocument[];
  offlineQueueCount: number;
  isOnline: boolean;

  // Actions
  addCapture: (dataUrl: string, blob: Blob, folderId?: string) => string;
  removeCapture: (id: string) => void;
  clearCaptures: () => void;
  uploadCapture: (id: string) => Promise<void>;
  uploadAll: () => Promise<void>;
  retryFailed: () => Promise<void>;

  // Sync
  syncOfflineQueue: () => Promise<void>;
  refreshQueueCount: () => Promise<void>;
}

// ==================== Hook ====================

export function useCameraScan(): UseCameraScanReturn {
  const [capturedDocuments, setCapturedDocuments] = useState<CapturedDocument[]>([]);
  const [offlineQueueCount, setOfflineQueueCount] = useState(0);
  const [isOnline, setIsOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);
  const queryClient = useQueryClient();

  // ==================== Online Status ====================

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      toast.success('Verbindung wiederhergestellt', {
        description: 'Offline-Dokumente werden synchronisiert...',
      });
      // Trigger sync
      syncOfflineQueue();
    };

    const handleOffline = () => {
      setIsOnline(false);
      toast.warning('Offline-Modus', {
        description: 'Dokumente werden lokal gespeichert.',
      });
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ==================== Queue Count ====================

  const refreshQueueCount = useCallback(async () => {
    try {
      const count = await getPendingMutationCount();
      setOfflineQueueCount(count);
    } catch (error) {
      logger.error('[useCameraScan] Fehler beim Laden der Warteschlange', { error });
    }
  }, []);

  useEffect(() => {
    refreshQueueCount();
  }, [refreshQueueCount]);

  // ==================== Capture Management ====================

  const addCapture = useCallback((dataUrl: string, blob: Blob, folderId?: string): string => {
    const id = crypto.randomUUID();
    const capture: CapturedDocument = {
      id,
      dataUrl,
      blob,
      timestamp: Date.now(),
      status: 'pending',
      folderId,
    };
    setCapturedDocuments((prev) => [...prev, capture]);
    logger.info('[useCameraScan] Bild hinzugefuegt', { id });
    return id;
  }, []);

  const removeCapture = useCallback((id: string) => {
    setCapturedDocuments((prev) => prev.filter((doc) => doc.id !== id));
    logger.info('[useCameraScan] Bild entfernt', { id });
  }, []);

  const clearCaptures = useCallback(() => {
    setCapturedDocuments([]);
    logger.info('[useCameraScan] Alle Bilder geloescht');
  }, []);

  // ==================== Upload ====================

  const uploadCapture = useCallback(
    async (id: string) => {
      const capture = capturedDocuments.find((doc) => doc.id === id);
      if (!capture) return;

      // Update status
      setCapturedDocuments((prev) =>
        prev.map((doc) => (doc.id === id ? { ...doc, status: 'uploading' as const } : doc))
      );

      try {
        // Check online status
        if (!navigator.onLine) {
          // Queue for later
          await addMutation({
            endpoint: '/api/v1/documents/upload',
            method: 'POST',
            payload: {
              folderId: capture.folderId,
              source: 'camera_scan',
              timestamp: capture.timestamp,
            },
            maxRetries: 3,
          });

          setCapturedDocuments((prev) =>
            prev.map((doc) => (doc.id === id ? { ...doc, status: 'pending' as const } : doc))
          );

          await refreshQueueCount();
          toast.info('In Warteschlange', {
            description: 'Das Dokument wird hochgeladen, sobald Sie online sind.',
          });
          return;
        }

        // Upload
        const formData = new FormData();
        formData.append('file', capture.blob, `scan-${capture.timestamp}.jpg`);
        if (capture.folderId) {
          formData.append('folder_id', capture.folderId);
        }
        formData.append('source', 'camera_scan');

        const response = await fetch('/api/v1/documents/upload', {
          method: 'POST',
          body: formData,
          credentials: 'include',
        });

        if (!response.ok) {
          throw new Error('Upload fehlgeschlagen');
        }

        // Success
        setCapturedDocuments((prev) =>
          prev.map((doc) => (doc.id === id ? { ...doc, status: 'uploaded' as const } : doc))
        );

        queryClient.invalidateQueries({ queryKey: ['documents'] });
        toast.success('Hochgeladen', { description: 'Dokument wird verarbeitet.' });

        logger.info('[useCameraScan] Upload erfolgreich', { id });
      } catch (error) {
        setCapturedDocuments((prev) =>
          prev.map((doc) =>
            doc.id === id
              ? {
                  ...doc,
                  status: 'failed' as const,
                  errorMessage: error instanceof Error ? error.message : 'Unbekannter Fehler',
                }
              : doc
          )
        );

        logger.error('[useCameraScan] Upload fehlgeschlagen', { id, error });
        toast.error('Upload fehlgeschlagen');
      }
    },
    [capturedDocuments, queryClient, refreshQueueCount]
  );

  const uploadAll = useCallback(async () => {
    const pending = capturedDocuments.filter((doc) => doc.status === 'pending');
    for (const doc of pending) {
      await uploadCapture(doc.id);
    }
  }, [capturedDocuments, uploadCapture]);

  const retryFailed = useCallback(async () => {
    const failed = capturedDocuments.filter((doc) => doc.status === 'failed');
    // Reset status to pending
    setCapturedDocuments((prev) =>
      prev.map((doc) => (doc.status === 'failed' ? { ...doc, status: 'pending' as const } : doc))
    );
    // Upload again
    for (const doc of failed) {
      await uploadCapture(doc.id);
    }
  }, [capturedDocuments, uploadCapture]);

  // ==================== Offline Sync ====================

  const syncOfflineQueue = useCallback(async () => {
    if (!navigator.onLine) return;

    try {
      const mutations = await getPendingMutations();
      logger.info('[useCameraScan] Syncing offline queue', { count: mutations.length });

      for (const mutation of mutations) {
        if (mutation.endpoint.includes('/documents/upload')) {
          try {
            // Note: For actual file uploads, the file data would need to be
            // stored separately in IndexedDB. This is a simplified version.
            const response = await fetch(mutation.endpoint, {
              method: mutation.method,
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify(mutation.payload),
              credentials: 'include',
            });

            if (response.ok) {
              await removeMutation(mutation.id);
              logger.info('[useCameraScan] Mutation synced', { id: mutation.id });
            }
          } catch (error) {
            logger.error('[useCameraScan] Mutation sync failed', { id: mutation.id, error });
          }
        }
      }

      await refreshQueueCount();
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    } catch (error) {
      logger.error('[useCameraScan] Offline sync failed', { error });
    }
  }, [queryClient, refreshQueueCount]);

  // Listen for SW sync message
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'SYNC_COMPLETE') {
        refreshQueueCount();
        queryClient.invalidateQueries({ queryKey: ['documents'] });
        toast.success('Synchronisation abgeschlossen');
      }
    };

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener('message', handleMessage);
      return () => {
        navigator.serviceWorker.removeEventListener('message', handleMessage);
      };
    }
  }, [queryClient, refreshQueueCount]);

  return {
    capturedDocuments,
    offlineQueueCount,
    isOnline,
    addCapture,
    removeCapture,
    clearCaptures,
    uploadCapture,
    uploadAll,
    retryFailed,
    syncOfflineQueue,
    refreshQueueCount,
  };
}

export default useCameraScan;
