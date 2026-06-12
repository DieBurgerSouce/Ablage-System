/**
 * Push Notifications Service
 *
 * Manages Web Push subscription and notification handling.
 *
 * Features:
 * - Request notification permission
 * - Register with backend for push
 * - Handle incoming notifications
 * - Deep linking to relevant content
 * - Preference management
 *
 * All user-facing text is in German.
 */

import { apiClient } from '@/lib/api/client';
import { logger } from '@/lib/logger';

// ============================================
// Types
// ============================================

export interface PushSubscriptionData {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
  expirationTime?: number | null;
}

export interface DeviceInfo {
  deviceName?: string;
  deviceType: 'mobile' | 'tablet' | 'desktop';
  browser: string;
  os: string;
}

export interface NotificationPreferences {
  documents?: boolean;
  approvals?: boolean;
  alerts?: boolean;
  system?: boolean;
  marketing?: boolean;
}

export interface PushNotificationOptions {
  title: string;
  body: string;
  icon?: string;
  badge?: string;
  image?: string;
  tag?: string;
  data?: Record<string, unknown>;
  actions?: Array<{ action: string; title: string; icon?: string }>;
  requireInteraction?: boolean;
  silent?: boolean;
}

// ============================================
// Constants
// ============================================

const VAPID_PUBLIC_KEY_STORAGE_KEY = 'vapid_public_key';
const SUBSCRIPTION_STORAGE_KEY = 'push_subscription_endpoint';

// ============================================
// Utility Functions
// ============================================

/**
 * Convert URL-safe base64 to Uint8Array for VAPID key
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');

  const rawData = window.atob(base64);
  // Expliziter ArrayBuffer: BufferSource verlangt Uint8Array<ArrayBuffer>
  const outputArray = new Uint8Array(new ArrayBuffer(rawData.length));

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/**
 * Detect device information
 */
function getDeviceInfo(): DeviceInfo {
  const ua = navigator.userAgent;

  // Detect device type
  let deviceType: 'mobile' | 'tablet' | 'desktop' = 'desktop';
  if (/Mobi|Android/i.test(ua)) {
    deviceType = 'mobile';
  } else if (/iPad|Tablet/i.test(ua)) {
    deviceType = 'tablet';
  }

  // Detect browser
  let browser = 'Unknown';
  if (ua.includes('Chrome')) browser = 'Chrome';
  else if (ua.includes('Firefox')) browser = 'Firefox';
  else if (ua.includes('Safari')) browser = 'Safari';
  else if (ua.includes('Edge')) browser = 'Edge';

  // Detect OS
  let os = 'Unknown';
  if (ua.includes('Windows')) os = 'Windows';
  else if (ua.includes('Mac')) os = 'macOS';
  else if (ua.includes('Linux')) os = 'Linux';
  else if (ua.includes('Android')) os = 'Android';
  else if (ua.includes('iOS') || ua.includes('iPhone') || ua.includes('iPad'))
    os = 'iOS';

  return {
    deviceType,
    browser,
    os,
  };
}

// ============================================
// Push Notification Service Class
// ============================================

class PushNotificationService {
  private vapidPublicKey: string | null = null;
  private subscription: PushSubscription | null = null;
  private serviceWorkerRegistration: ServiceWorkerRegistration | null = null;

  /**
   * Check if push notifications are supported
   */
  isSupported(): boolean {
    return (
      'serviceWorker' in navigator &&
      'PushManager' in window &&
      'Notification' in window
    );
  }

  /**
   * Get current notification permission status
   */
  getPermissionStatus(): NotificationPermission {
    if (!('Notification' in window)) {
      return 'denied';
    }
    return Notification.permission;
  }

  /**
   * Check if notifications are enabled
   */
  isEnabled(): boolean {
    return this.getPermissionStatus() === 'granted' && this.subscription !== null;
  }

  /**
   * Request notification permission
   */
  async requestPermission(): Promise<NotificationPermission> {
    if (!this.isSupported()) {
      logger.warn('[PushNotifications] Nicht unterstützt');
      return 'denied';
    }

    try {
      const permission = await Notification.requestPermission();
      logger.info('[PushNotifications] Berechtigung angefragt', { permission });
      return permission;
    } catch (error) {
      logger.error('[PushNotifications] Berechtigungsanfrage fehlgeschlagen', {
        error,
      });
      return 'denied';
    }
  }

  /**
   * Get VAPID public key from backend
   */
  async getVAPIDPublicKey(): Promise<string> {
    // Check cache first
    if (this.vapidPublicKey) {
      return this.vapidPublicKey;
    }

    // Check localStorage
    const cached = localStorage.getItem(VAPID_PUBLIC_KEY_STORAGE_KEY);
    if (cached) {
      this.vapidPublicKey = cached;
      return cached;
    }

    try {
      const response = await apiClient.get('/push/vapid-public-key');
      const publicKey = response.data.public_key;

      // Cache the key
      this.vapidPublicKey = publicKey;
      localStorage.setItem(VAPID_PUBLIC_KEY_STORAGE_KEY, publicKey);

      logger.info('[PushNotifications] VAPID Key abgerufen');
      return publicKey;
    } catch (error) {
      logger.error('[PushNotifications] VAPID Key Abruf fehlgeschlagen', {
        error,
      });
      throw new Error('VAPID Public Key konnte nicht abgerufen werden');
    }
  }

  /**
   * Get service worker registration
   */
  async getServiceWorkerRegistration(): Promise<ServiceWorkerRegistration> {
    if (this.serviceWorkerRegistration) {
      return this.serviceWorkerRegistration;
    }

    this.serviceWorkerRegistration = await navigator.serviceWorker.ready;
    return this.serviceWorkerRegistration;
  }

  /**
   * Subscribe to push notifications
   */
  async subscribe(
    deviceName?: string
  ): Promise<{ success: boolean; message: string }> {
    if (!this.isSupported()) {
      return {
        success: false,
        message: 'Push-Benachrichtigungen werden nicht unterstützt',
      };
    }

    // Check permission
    const permission = await this.requestPermission();
    if (permission !== 'granted') {
      return {
        success: false,
        message: 'Berechtigung für Benachrichtigungen wurde verweigert',
      };
    }

    try {
      // Get VAPID key and service worker
      const [vapidPublicKey, registration] = await Promise.all([
        this.getVAPIDPublicKey(),
        this.getServiceWorkerRegistration(),
      ]);

      // Check for existing subscription
      let subscription = await registration.pushManager.getSubscription();

      // Create new subscription if none exists
      if (!subscription) {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
        });
      }

      this.subscription = subscription;

      // Get device info
      const deviceInfo = getDeviceInfo();

      // Register with backend
      const subscriptionJson = subscription.toJSON();
      await apiClient.post('/push/subscriptions', {
        endpoint: subscriptionJson.endpoint,
        keys: {
          p256dh: subscriptionJson.keys?.p256dh,
          auth: subscriptionJson.keys?.auth,
        },
        expiration_time: subscription.expirationTime,
        device_name: deviceName,
        ...deviceInfo,
      });

      // Store endpoint locally
      localStorage.setItem(
        SUBSCRIPTION_STORAGE_KEY,
        subscriptionJson.endpoint || ''
      );

      logger.info('[PushNotifications] Erfolgreich registriert', {
        deviceType: deviceInfo.deviceType,
      });

      return {
        success: true,
        message: 'Push-Benachrichtigungen erfolgreich aktiviert',
      };
    } catch (error) {
      logger.error('[PushNotifications] Registrierung fehlgeschlagen', { error });
      return {
        success: false,
        message: 'Registrierung fehlgeschlagen. Bitte versuchen Sie es erneut.',
      };
    }
  }

  /**
   * Unsubscribe from push notifications
   */
  async unsubscribe(): Promise<{ success: boolean; message: string }> {
    try {
      const registration = await this.getServiceWorkerRegistration();
      const subscription = await registration.pushManager.getSubscription();

      if (subscription) {
        // Unsubscribe from browser
        await subscription.unsubscribe();

        // Unregister from backend
        await apiClient.delete('/push/subscriptions', {
          params: { endpoint: subscription.endpoint },
        });

        this.subscription = null;
        localStorage.removeItem(SUBSCRIPTION_STORAGE_KEY);

        logger.info('[PushNotifications] Erfolgreich abgemeldet');
      }

      return {
        success: true,
        message: 'Push-Benachrichtigungen deaktiviert',
      };
    } catch (error) {
      logger.error('[PushNotifications] Abmeldung fehlgeschlagen', { error });
      return {
        success: false,
        message: 'Abmeldung fehlgeschlagen',
      };
    }
  }

  /**
   * Update notification preferences
   */
  async updatePreferences(
    subscriptionId: string,
    preferences: NotificationPreferences
  ): Promise<{ success: boolean }> {
    try {
      await apiClient.patch(
        `/push/subscriptions/${subscriptionId}/preferences`,
        { preferences }
      );

      logger.info('[PushNotifications] Einstellungen aktualisiert', {
        preferences,
      });

      return { success: true };
    } catch (error) {
      logger.error('[PushNotifications] Einstellungen-Update fehlgeschlagen', {
        error,
      });
      return { success: false };
    }
  }

  /**
   * Get all subscriptions for current user
   */
  async getSubscriptions(): Promise<
    Array<{
      id: string;
      deviceName: string | null;
      deviceType: string | null;
      browser: string | null;
      os: string | null;
      preferences: NotificationPreferences;
      isActive: boolean;
      createdAt: string;
      lastUsedAt: string | null;
    }>
  > {
    try {
      const response = await apiClient.get('/push/subscriptions');
      return response.data;
    } catch (error) {
      logger.error('[PushNotifications] Abruf der Subscriptions fehlgeschlagen', {
        error,
      });
      return [];
    }
  }

  /**
   * Show a local notification (for testing or when app is in foreground)
   */
  async showLocalNotification(
    options: PushNotificationOptions
  ): Promise<boolean> {
    if (this.getPermissionStatus() !== 'granted') {
      return false;
    }

    try {
      const registration = await this.getServiceWorkerRegistration();

      // image/actions sind Service-Worker-Erweiterungen ausserhalb des
      // DOM-NotificationOptions-Typs — daher erweitert typisiert.
      await registration.showNotification(options.title, {
        body: options.body,
        icon: options.icon || '/icons/icon-192x192.png',
        badge: options.badge || '/icons/icon-72x72.png',
        image: options.image,
        tag: options.tag,
        data: options.data,
        actions: options.actions,
        requireInteraction: options.requireInteraction,
        silent: options.silent,
        vibrate: [200, 100, 200],
      } as NotificationOptions);

      return true;
    } catch (error) {
      logger.error('[PushNotifications] Lokale Benachrichtigung fehlgeschlagen', {
        error,
      });
      return false;
    }
  }

  /**
   * Track notification click
   */
  async trackClick(subscriptionId: string, tag: string): Promise<void> {
    try {
      await apiClient.post('/push/track-click', {
        tag,
      }, {
        params: { subscription_id: subscriptionId },
      });
    } catch (error) {
      logger.error('[PushNotifications] Click-Tracking fehlgeschlagen', {
        error,
      });
    }
  }

  /**
   * Send test notification (development only)
   */
  async sendTestNotification(): Promise<{ success: boolean; message: string }> {
    try {
      await apiClient.post('/push/test');
      return {
        success: true,
        message: 'Test-Benachrichtigung gesendet',
      };
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : 'Unbekannter Fehler';
      return {
        success: false,
        message: `Test fehlgeschlagen: ${errorMessage}`,
      };
    }
  }
}

// ============================================
// Singleton Export
// ============================================

export const pushNotifications = new PushNotificationService();

// ============================================
// React Hook
// ============================================

import { useState, useEffect, useCallback } from 'react';

export interface UsePushNotificationsResult {
  /** Whether push notifications are supported */
  isSupported: boolean;
  /** Current permission status */
  permission: NotificationPermission;
  /** Whether currently subscribed */
  isSubscribed: boolean;
  /** Loading state */
  isLoading: boolean;
  /** Subscribe to push notifications */
  subscribe: (deviceName?: string) => Promise<{ success: boolean; message: string }>;
  /** Unsubscribe from push notifications */
  unsubscribe: () => Promise<{ success: boolean; message: string }>;
  /** Request permission only */
  requestPermission: () => Promise<NotificationPermission>;
  /** Send test notification */
  sendTest: () => Promise<{ success: boolean; message: string }>;
}

export function usePushNotifications(): UsePushNotificationsResult {
  const [permission, setPermission] = useState<NotificationPermission>(
    pushNotifications.getPermissionStatus()
  );
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Check subscription status on mount
  useEffect(() => {
    const checkSubscription = async () => {
      if (!pushNotifications.isSupported()) {
        setIsLoading(false);
        return;
      }

      try {
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.getSubscription();
        setIsSubscribed(subscription !== null);
      } catch {
        setIsSubscribed(false);
      } finally {
        setIsLoading(false);
      }
    };

    checkSubscription();
  }, []);

  // Listen for permission changes
  useEffect(() => {
    const handlePermissionChange = () => {
      setPermission(pushNotifications.getPermissionStatus());
    };

    // Some browsers support this event
    if ('permissions' in navigator) {
      navigator.permissions
        .query({ name: 'notifications' })
        .then((permissionStatus) => {
          permissionStatus.onchange = handlePermissionChange;
        })
        .catch(() => {
          // Ignore errors
        });
    }
  }, []);

  const subscribe = useCallback(async (deviceName?: string) => {
    setIsLoading(true);
    const result = await pushNotifications.subscribe(deviceName);
    setIsSubscribed(result.success);
    setPermission(pushNotifications.getPermissionStatus());
    setIsLoading(false);
    return result;
  }, []);

  const unsubscribe = useCallback(async () => {
    setIsLoading(true);
    const result = await pushNotifications.unsubscribe();
    setIsSubscribed(!result.success);
    setIsLoading(false);
    return result;
  }, []);

  const requestPermission = useCallback(async () => {
    const result = await pushNotifications.requestPermission();
    setPermission(result);
    return result;
  }, []);

  const sendTest = useCallback(async () => {
    return pushNotifications.sendTestNotification();
  }, []);

  return {
    isSupported: pushNotifications.isSupported(),
    permission,
    isSubscribed,
    isLoading,
    subscribe,
    unsubscribe,
    requestPermission,
    sendTest,
  };
}

export default pushNotifications;
