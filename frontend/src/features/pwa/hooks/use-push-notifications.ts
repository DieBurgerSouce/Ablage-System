/**
 * usePushNotifications Hook
 *
 * Provides push notification management with React Query integration.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { getPushSubscriptions, updateSubscriptionPreferences, subscribeToPushNotifications, unsubscribeFromPushNotifications, sendTestNotification, getSubscriptionStats } from '../api/push-api'
import { logger } from '@/lib/logger'

// ==================================================
// Query Keys
// ==================================================

export const pushNotificationKeys = {
  all: ['push-notifications'] as const,
  subscriptions: () => [...pushNotificationKeys.all, 'subscriptions'] as const,
  stats: () => [...pushNotificationKeys.all, 'stats'] as const,
}

// ==================================================
// Queries
// ==================================================

/**
 * Get all push subscriptions for current user
 */
export function usePushSubscriptions(includeInactive = false) {
  return useQuery({
    queryKey: [...pushNotificationKeys.subscriptions(), includeInactive],
    queryFn: () => getPushSubscriptions(includeInactive),
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}

/**
 * Get subscription statistics
 */
export function usePushSubscriptionStats() {
  return useQuery({
    queryKey: pushNotificationKeys.stats(),
    queryFn: getSubscriptionStats,
    staleTime: 5 * 60 * 1000,
  })
}

// ==================================================
// Mutations
// ==================================================

/**
 * Subscribe to push notifications
 */
export function useSubscribeToPush() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: subscribeToPushNotifications,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pushNotificationKeys.subscriptions() })
      toast.success('Push-Benachrichtigungen aktiviert', {
        description: 'Sie erhalten jetzt Benachrichtigungen auf diesem Gerät',
      })
      logger.info('[usePushNotifications] Subscription erfolgreich')
    },
    onError: (error) => {
      logger.error('[usePushNotifications] Subscription fehlgeschlagen', { error })
      if (error instanceof Error && error.message.includes('denied')) {
        toast.error('Benachrichtigungen blockiert', {
          description: 'Bitte erlauben Sie Benachrichtigungen in den Browser-Einstellungen',
        })
      } else {
        toast.error('Aktivierung fehlgeschlagen', {
          description: 'Push-Benachrichtigungen konnten nicht aktiviert werden',
        })
      }
    },
  })
}

/**
 * Unsubscribe from push notifications
 */
export function useUnsubscribeFromPush() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: unsubscribeFromPushNotifications,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pushNotificationKeys.subscriptions() })
      toast.success('Push-Benachrichtigungen deaktiviert')
      logger.info('[usePushNotifications] Unsubscription erfolgreich')
    },
    onError: (error) => {
      logger.error('[usePushNotifications] Unsubscription fehlgeschlagen', { error })
      toast.error('Deaktivierung fehlgeschlagen')
    },
  })
}

/**
 * Update notification preferences
 */
export function useUpdatePushPreferences() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      subscriptionId,
      preferences,
    }: {
      subscriptionId: string
      preferences: Record<string, boolean>
    }) => updateSubscriptionPreferences(subscriptionId, preferences),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pushNotificationKeys.subscriptions() })
      toast.success('Einstellungen gespeichert')
    },
    onError: () => {
      toast.error('Speichern fehlgeschlagen')
    },
  })
}

/**
 * Send test notification (dev only)
 */
export function useSendTestNotification() {
  return useMutation({
    mutationFn: sendTestNotification,
    onSuccess: () => {
      toast.info('Test-Benachrichtigung gesendet')
    },
    onError: () => {
      toast.error('Test fehlgeschlagen', {
        description: 'Keine aktiven Subscriptions oder Entwicklungsmodus nicht aktiv',
      })
    },
  })
}

// ==================================================
// Helpers
// ==================================================

/**
 * Check if push notifications are supported and available
 */
export function isPushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

/**
 * Check current notification permission status
 */
export function getNotificationPermission(): NotificationPermission {
  if (!('Notification' in window)) {
    return 'denied'
  }
  return Notification.permission
}

/**
 * Request notification permission
 */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) {
    return 'denied'
  }

  if (Notification.permission === 'granted') {
    return 'granted'
  }

  if (Notification.permission === 'denied') {
    return 'denied'
  }

  return await Notification.requestPermission()
}
