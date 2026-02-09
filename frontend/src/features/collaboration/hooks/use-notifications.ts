/**
 * useNotifications - Hook fuer Benutzer-Benachrichtigungen
 *
 * Laedt, markiert als gelesen und verwaltet Benachrichtigungen.
 * Integriert mit Backend API: /api/v1/notifications
 *
 * Enterprise Features:
 * - Error Handling mit Toast-Benachrichtigungen
 * - Optimistic Updates mit Rollback bei Fehler
 * - Visibility-aware Refetch (pausiert bei inaktivem Tab)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import type { NotificationsResponse } from '../types/collaboration.types';

// ==================== API Functions ====================

async function fetchNotifications(): Promise<NotificationsResponse> {
  const response = await apiClient.get<NotificationsResponse>('/notifications');
  return response.data;
}

async function markAsRead(notificationId: string): Promise<void> {
  await apiClient.patch(`/notifications/${notificationId}/read`);
}

async function markAllAsRead(): Promise<void> {
  await apiClient.post('/notifications/mark-all-read');
}

async function deleteNotification(notificationId: string): Promise<void> {
  await apiClient.delete(`/notifications/${notificationId}`);
}

// ==================== Hooks ====================

export function useNotifications() {
  return useQuery({
    queryKey: ['notifications'],
    queryFn: fetchNotifications,
    staleTime: 30000, // 30 seconds
    // Visibility-aware Refetch: Pausiert bei inaktivem Tab
    refetchInterval: (_query) => {
      // Nur refetchen wenn Tab aktiv ist
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return false;
      }
      return 60000; // Refetch every minute for real-time-ish updates
    },
    refetchOnWindowFocus: true,
  });
}

export function useMarkAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: markAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
    onError: (error: Error) => {
      toast.error('Fehler beim Markieren als gelesen', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
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
    onError: (error: Error, _, context) => {
      // Rollback bei Fehler
      if (context?.previousData) {
        queryClient.setQueryData(['notifications'], context.previousData);
      }
      toast.error('Fehler beim Markieren aller als gelesen', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
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
    onError: (error: Error) => {
      toast.error('Fehler beim Löschen der Benachrichtigung', {
        description: error.message || 'Bitte versuchen Sie es erneut.',
      });
    },
  });
}
