/**
 * Push Notifications API Client
 *
 * Provides functions for managing Web Push subscriptions.
 */

import { apiClient } from '@/lib/api/client'
import { logger } from '@/lib/logger'

// ==================================================
// Types
// ==================================================

export interface PushSubscriptionKeys {
  p256dh: string
  auth: string
}

export interface PushSubscriptionCreate {
  endpoint: string
  keys: PushSubscriptionKeys
  expiration_time?: number
  device_name?: string
  device_type?: 'mobile' | 'tablet' | 'desktop'
  browser?: string
  os?: string
}

export interface PushSubscriptionResponse {
  id: string
  endpoint: string
  device_name?: string
  device_type?: string
  browser?: string
  os?: string
  preferences: Record<string, boolean>
  is_active: boolean
  created_at: string
  last_used_at?: string
}

export interface SubscriptionStats {
  total: number
  active: number
  inactive: number
  by_device_type: Record<string, number>
}

// ==================================================
// API Functions
// ==================================================

/**
 * Get the VAPID public key for push subscriptions
 */
export async function getVapidPublicKey(): Promise<string> {
  const response = await apiClient.get<{ public_key: string }>('/push/vapid-public-key')
  return response.data.public_key
}

/**
 * Register a push subscription
 */
export async function registerPushSubscription(
  subscription: PushSubscriptionCreate
): Promise<PushSubscriptionResponse> {
  const response = await apiClient.post<PushSubscriptionResponse>(
    '/push/subscriptions',
    subscription
  )
  return response.data
}

/**
 * Unregister a push subscription
 */
export async function unregisterPushSubscription(endpoint: string): Promise<void> {
  await apiClient.delete('/push/subscriptions', {
    params: { endpoint },
  })
}

/**
 * Get all push subscriptions for current user
 */
export async function getPushSubscriptions(
  includeInactive = false
): Promise<PushSubscriptionResponse[]> {
  const response = await apiClient.get<PushSubscriptionResponse[]>('/push/subscriptions', {
    params: { include_inactive: includeInactive },
  })
  return response.data
}

/**
 * Update subscription preferences
 */
export async function updateSubscriptionPreferences(
  subscriptionId: string,
  preferences: Record<string, boolean>
): Promise<PushSubscriptionResponse> {
  const response = await apiClient.patch<PushSubscriptionResponse>(
    `/push/subscriptions/${subscriptionId}/preferences`,
    { preferences }
  )
  return response.data
}

/**
 * Get subscription statistics
 */
export async function getSubscriptionStats(): Promise<SubscriptionStats> {
  const response = await apiClient.get<SubscriptionStats>('/push/stats')
  return response.data
}

/**
 * Track a notification click
 */
export async function trackNotificationClick(
  subscriptionId: string,
  tag: string
): Promise<void> {
  await apiClient.post('/push/track-click', { tag }, {
    params: { subscription_id: subscriptionId },
  })
}

/**
 * Send a test notification (dev only)
 */
export async function sendTestNotification(): Promise<void> {
  await apiClient.post('/push/test')
}

// ==================================================
// Helper Functions
// ==================================================

/**
 * Convert a PushSubscription to the API format
 */
export function formatSubscriptionForApi(
  subscription: PushSubscription,
  deviceInfo?: { name?: string; type?: 'mobile' | 'tablet' | 'desktop' }
): PushSubscriptionCreate {
  const keys = subscription.toJSON().keys

  if (!keys?.p256dh || !keys?.auth) {
    throw new Error('Push subscription is missing keys')
  }

  // Detect device type from user agent
  const userAgent = navigator.userAgent
  let deviceType: 'mobile' | 'tablet' | 'desktop' = 'desktop'
  if (/Android|iPhone|iPod/.test(userAgent)) {
    deviceType = 'mobile'
  } else if (/iPad|Tablet/.test(userAgent)) {
    deviceType = 'tablet'
  }

  // Detect browser
  let browser = 'Unknown'
  if (/Chrome/.test(userAgent)) {
    browser = 'Chrome'
  } else if (/Firefox/.test(userAgent)) {
    browser = 'Firefox'
  } else if (/Safari/.test(userAgent)) {
    browser = 'Safari'
  } else if (/Edge/.test(userAgent)) {
    browser = 'Edge'
  }

  // Detect OS
  let os = 'Unknown'
  if (/Windows/.test(userAgent)) {
    os = 'Windows'
  } else if (/Mac OS/.test(userAgent)) {
    os = 'macOS'
  } else if (/Linux/.test(userAgent)) {
    os = 'Linux'
  } else if (/Android/.test(userAgent)) {
    os = 'Android'
  } else if (/iOS|iPhone|iPad/.test(userAgent)) {
    os = 'iOS'
  }

  return {
    endpoint: subscription.endpoint,
    keys: {
      p256dh: keys.p256dh,
      auth: keys.auth,
    },
    expiration_time: subscription.expirationTime ?? undefined,
    device_name: deviceInfo?.name,
    device_type: deviceInfo?.type ?? deviceType,
    browser,
    os,
  }
}

/**
 * Request and register push notifications
 */
export async function subscribeToPushNotifications(): Promise<PushSubscriptionResponse | null> {
  // Check if push notifications are supported
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    logger.warn('[PushAPI] Push notifications not supported')
    return null
  }

  try {
    // Get VAPID public key
    const vapidKey = await getVapidPublicKey()

    // Get service worker registration
    const registration = await navigator.serviceWorker.ready

    // Check existing subscription
    let subscription = await registration.pushManager.getSubscription()

    if (!subscription) {
      // Request new subscription
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      })
    }

    // Register with backend
    const formattedSubscription = formatSubscriptionForApi(subscription)
    const response = await registerPushSubscription(formattedSubscription)

    logger.info('[PushAPI] Push subscription registered')
    return response
  } catch (error) {
    logger.error('[PushAPI] Failed to subscribe', { error })
    throw error
  }
}

/**
 * Unsubscribe from push notifications
 */
export async function unsubscribeFromPushNotifications(): Promise<void> {
  if (!('serviceWorker' in navigator)) {
    return
  }

  try {
    const registration = await navigator.serviceWorker.ready
    const subscription = await registration.pushManager.getSubscription()

    if (subscription) {
      // Unsubscribe from browser
      await subscription.unsubscribe()

      // Unregister from backend
      await unregisterPushSubscription(subscription.endpoint)

      logger.info('[PushAPI] Push subscription removed')
    }
  } catch (error) {
    logger.error('[PushAPI] Failed to unsubscribe', { error })
    throw error
  }
}

/**
 * Convert URL-safe base64 to Uint8Array (for applicationServerKey)
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')

  const rawData = window.atob(base64)
  // Expliziter ArrayBuffer: BufferSource verlangt Uint8Array<ArrayBuffer>
  const outputArray = new Uint8Array(new ArrayBuffer(rawData.length))

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }

  return outputArray
}
