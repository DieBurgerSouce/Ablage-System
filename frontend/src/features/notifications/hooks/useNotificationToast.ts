/**
 * Real-time Notification Toast Hook
 *
 * Abonniert WebSocket-Events vom Typ 'notification.received'
 * und zeigt Toast-Benachrichtigungen via sonner an.
 * Invalidiert automatisch die Notification-Query-Caches
 * (Unread Count + Listen), damit die NotificationBell aktuell bleibt.
 */

import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useRealtimeEvent, type RealtimeEvent } from '@/lib/websocket';
import { notificationKeys } from './useNotifications';

interface NotificationPayload {
  title: string;
  message: string;
  priority: string;
  notification_type: string;
}

export function useNotificationToast() {
  const queryClient = useQueryClient();

  const handleNotification = useCallback((event: RealtimeEvent) => {
    const { title, message, priority } = event.payload as unknown as NotificationPayload;

    // Nachricht kuerzen falls zu lang
    const truncatedMessage =
      typeof message === 'string' && message.length > 150
        ? message.substring(0, 150) + '...'
        : message;

    // Prioritaet auf sonner Toast-Variante mappen
    switch (priority) {
      case 'critical':
        toast.error(title, { description: truncatedMessage, duration: 10000 });
        break;
      case 'high':
        toast.warning(title, { description: truncatedMessage, duration: 8000 });
        break;
      default:
        toast.info(title, { description: truncatedMessage, duration: 5000 });
        break;
    }

    // Notification-Queries invalidieren fuer Badge-Update
    queryClient.invalidateQueries({ queryKey: notificationKeys.unreadCount() });
    queryClient.invalidateQueries({ queryKey: notificationKeys.lists() });
  }, [queryClient]);

  // WebSocket-Event 'notification.received' abonnieren
  useRealtimeEvent('notification.received', handleNotification);
}
