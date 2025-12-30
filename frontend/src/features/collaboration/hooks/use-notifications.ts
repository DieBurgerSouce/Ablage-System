/**
 * useNotifications - Hook fuer Benutzer-Benachrichtigungen
 *
 * Laedt, markiert als gelesen und verwaltet Benachrichtigungen.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { Notification, NotificationsResponse } from '../types/collaboration.types';

// ==================== Mock Data ====================

const MOCK_NOTIFICATIONS: Notification[] = [
  {
    id: 'notif-1',
    type: 'mention',
    title: 'Erwaehnung',
    message: 'Max Mustermann hat Sie in einem Kommentar erwaehnt',
    documentId: 'doc-1',
    documentName: 'Rechnung_2024_001.pdf',
    fromUserId: 'user-1',
    fromUserName: 'Max Mustermann',
    isRead: false,
    createdAt: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    actionUrl: '/documents/doc-1',
  },
  {
    id: 'notif-2',
    type: 'comment_reply',
    title: 'Antwort auf Kommentar',
    message: 'Anna Schmidt hat auf Ihren Kommentar geantwortet',
    documentId: 'doc-2',
    documentName: 'Lieferschein_2024_042.pdf',
    fromUserId: 'user-2',
    fromUserName: 'Anna Schmidt',
    isRead: false,
    createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    actionUrl: '/documents/doc-2',
  },
  {
    id: 'notif-3',
    type: 'document_approved',
    title: 'Dokument freigegeben',
    message: 'Thomas Mueller hat Ihr Dokument freigegeben',
    documentId: 'doc-3',
    documentName: 'Angebot_Kunde_XYZ.pdf',
    fromUserId: 'user-3',
    fromUserName: 'Thomas Mueller',
    isRead: true,
    createdAt: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    actionUrl: '/documents/doc-3',
  },
  {
    id: 'notif-4',
    type: 'task_assigned',
    title: 'Aufgabe zugewiesen',
    message: 'Sie wurden zur Pruefung einer Rechnung zugewiesen',
    documentId: 'doc-4',
    documentName: 'Eingangsrechnung_Lieferant.pdf',
    fromUserId: 'system',
    fromUserName: 'System',
    isRead: true,
    createdAt: new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString(),
    actionUrl: '/documents/doc-4',
  },
];

// ==================== API Functions ====================

async function fetchNotifications(): Promise<NotificationsResponse> {
  // TODO: Replace with actual API call
  // const response = await apiClient.get<NotificationsResponse>('/notifications');
  // return response.data;

  await new Promise((resolve) => setTimeout(resolve, 200));

  const unreadCount = MOCK_NOTIFICATIONS.filter((n) => !n.isRead).length;

  return {
    notifications: MOCK_NOTIFICATIONS,
    unreadCount,
    total: MOCK_NOTIFICATIONS.length,
  };
}

async function markAsRead(notificationId: string): Promise<void> {
  // TODO: Replace with actual API call
  // await apiClient.patch(`/notifications/${notificationId}/read`);
  await new Promise((resolve) => setTimeout(resolve, 100));
}

async function markAllAsRead(): Promise<void> {
  // TODO: Replace with actual API call
  // await apiClient.patch('/notifications/read-all');
  await new Promise((resolve) => setTimeout(resolve, 100));
}

async function deleteNotification(notificationId: string): Promise<void> {
  // TODO: Replace with actual API call
  // await apiClient.delete(`/notifications/${notificationId}`);
  await new Promise((resolve) => setTimeout(resolve, 100));
}

// ==================== Hooks ====================

export function useNotifications() {
  return useQuery({
    queryKey: ['notifications'],
    queryFn: fetchNotifications,
    staleTime: 30000, // 30 seconds
    refetchInterval: 60000, // Refetch every minute for real-time-ish updates
  });
}

export function useMarkAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: markAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

export function useMarkAllAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: markAllAsRead,
    onMutate: async () => {
      // Optimistic update
      await queryClient.cancelQueries({ queryKey: ['notifications'] });
      const previousData = queryClient.getQueryData<NotificationsResponse>(['notifications']);

      if (previousData) {
        queryClient.setQueryData<NotificationsResponse>(['notifications'], {
          ...previousData,
          notifications: previousData.notifications.map((n) => ({ ...n, isRead: true })),
          unreadCount: 0,
        });
      }

      return { previousData };
    },
    onError: (_, __, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(['notifications'], context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

export function useDeleteNotification() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteNotification,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}
