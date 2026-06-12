/**
 * usePWAFeatures Hook
 *
 * Central hook for managing all PWA features:
 * - Service worker registration
 * - Update notifications
 * - Background sync
 * - Install prompt
 */

import { useState, useEffect, useCallback } from 'react';
import { useRegisterSW } from 'virtual:pwa-register/react';
import { logger } from '@/lib/logger';

export interface PWAUpdateInfo {
  available: boolean;
  offlineReady: boolean;
}

export interface UsePWAFeaturesResult {
  /** Service worker registration state */
  isRegistered: boolean;
  /** Update available */
  updateAvailable: boolean;
  /** App is ready for offline use */
  offlineReady: boolean;
  /** Trigger service worker update */
  updateServiceWorker: () => void;
  /** Register for background sync */
  registerBackgroundSync: (tag: string) => Promise<boolean>;
  /** Skip waiting (force update) */
  skipWaiting: () => void;
  /** Registration error if any */
  registrationError: Error | null;
}

export function usePWAFeatures(): UsePWAFeaturesResult {
  const [isRegistered, setIsRegistered] = useState(false);
  const [registrationError, setRegistrationError] = useState<Error | null>(null);

  // Use VitePWA's register hook
  const {
    needRefresh: [needRefresh, _setNeedRefresh],
    offlineReady: [offlineReady, _setOfflineReady],
    updateServiceWorker,
  } = useRegisterSW({
    onRegistered(registration) {
      logger.info('[PWA] Service Worker registriert', {
        scope: registration?.scope,
      });
      setIsRegistered(true);

      // Check for updates periodically (every 60 minutes)
      if (registration) {
        setInterval(() => {
          registration.update();
        }, 60 * 60 * 1000);
      }
    },
    onRegisterError(error) {
      logger.error('[PWA] Service Worker Registrierung fehlgeschlagen', {
        error,
      });
      setRegistrationError(error);
    },
    onNeedRefresh() {
      logger.info('[PWA] Neues Update verfügbar');
    },
    onOfflineReady() {
      logger.info('[PWA] App ist offline-bereit');
    },
  });

  /**
   * Register for background sync
   */
  const registerBackgroundSync = useCallback(
    async (tag: string): Promise<boolean> => {
      if (!('serviceWorker' in navigator)) {
        logger.warn('[PWA] Service Worker nicht unterstützt');
        return false;
      }

      try {
        const registration = await navigator.serviceWorker.ready;

        // Check if Background Sync API is available
        if ('sync' in registration) {
          // Background-Sync-API fehlt in den DOM-Lib-Typen (extern erzwungener Cast)
          await (registration as unknown as { sync: { register: (tag: string) => Promise<void> } }).sync.register(tag);
          logger.info('[PWA] Background Sync registriert', { tag });
          return true;
        }

        logger.warn('[PWA] Background Sync API nicht unterstützt');
        return false;
      } catch (error) {
        logger.error('[PWA] Background Sync Registrierung fehlgeschlagen', {
          tag,
          error,
        });
        return false;
      }
    },
    []
  );

  /**
   * Skip waiting to activate new service worker immediately
   */
  const skipWaiting = useCallback(() => {
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({
        type: 'SKIP_WAITING',
      });
    }
  }, []);

  // Listen for service worker messages
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;

    const handleMessage = (event: MessageEvent) => {
      if (event.data && event.data.type === 'SYNC_COMPLETE') {
        logger.info('[PWA] Background Sync abgeschlossen', {
          timestamp: event.data.timestamp,
        });
        // Could dispatch an event or update state here
        window.dispatchEvent(new CustomEvent('background-sync-complete'));
      }
    };

    navigator.serviceWorker.addEventListener('message', handleMessage);

    return () => {
      navigator.serviceWorker.removeEventListener('message', handleMessage);
    };
  }, []);

  return {
    isRegistered,
    updateAvailable: needRefresh,
    offlineReady,
    updateServiceWorker: () => updateServiceWorker(true),
    registerBackgroundSync,
    skipWaiting,
    registrationError,
  };
}

export default usePWAFeatures;
