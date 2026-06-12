/**
 * useNotificationNavigation Hook
 *
 * Handles deep linking from push notifications to app routes.
 * Listens for service worker messages and navigates accordingly.
 *
 * All user-facing text is in German.
 */

import { useEffect, useCallback } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { logger } from '@/lib/logger';

export interface NotificationClickData {
  url: string;
  type?: string;
  documentId?: string;
  entityId?: string;
  action?: string;
  timestamp?: number;
}

export interface UseNotificationNavigationOptions {
  /** Called when a notification navigation occurs */
  onNavigate?: (data: NotificationClickData) => void;
  /** Enabled (default: true) */
  enabled?: boolean;
}

/**
 * Hook to handle navigation from push notification clicks
 *
 * @example
 * ```tsx
 * function App() {
 *   useNotificationNavigation({
 *     onNavigate: (data) => {
 *       console.log('Navigating from notification:', data);
 *     },
 *   });
 *
 *   return <Router />;
 * }
 * ```
 */
export function useNotificationNavigation(
  options: UseNotificationNavigationOptions = {}
): void {
  const { onNavigate, enabled = true } = options;
  const navigate = useNavigate();

  /**
   * Handle notification click message from service worker
   */
  const handleServiceWorkerMessage = useCallback(
    (event: MessageEvent) => {
      if (!event.data || event.data.type !== 'NOTIFICATION_CLICK') {
        return;
      }

      const { url, data } = event.data as {
        type: string;
        url: string;
        data: NotificationClickData;
      };

      logger.info('[NotificationNavigation] Received click from SW', {
        url,
        type: data?.type,
      });

      // Call callback if provided
      onNavigate?.({ ...data, url });

      // Navigate to the URL
      if (url && url.startsWith('/')) {
        navigate({ to: url });
      }
    },
    [navigate, onNavigate]
  );

  /**
   * Handle notification click from URL params (when app opens from closed state)
   */
  const handleInitialNavigation = useCallback(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const notificationUrl = urlParams.get('notification_url');
    const notificationType = urlParams.get('notification_type');

    if (notificationUrl) {
      logger.info('[NotificationNavigation] Initial navigation from notification', {
        url: notificationUrl,
        type: notificationType,
      });

      onNavigate?.({
        url: notificationUrl,
        type: notificationType || undefined,
      });

      // Clean up URL params
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, '', cleanUrl);

      // Navigate
      navigate({ to: notificationUrl });
    }
  }, [navigate, onNavigate]);

  useEffect(() => {
    if (!enabled) return;
    if (!('serviceWorker' in navigator)) return;

    // Listen for messages from service worker
    navigator.serviceWorker.addEventListener('message', handleServiceWorkerMessage);

    // Handle initial navigation (app opened from notification)
    handleInitialNavigation();

    return () => {
      navigator.serviceWorker.removeEventListener(
        'message',
        handleServiceWorkerMessage
      );
    };
  }, [enabled, handleServiceWorkerMessage, handleInitialNavigation]);
}

export default useNotificationNavigation;
