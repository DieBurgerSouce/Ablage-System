/**
 * Notification Center - React Query Hooks
 *
 * TanStack Query Hooks für State Management
 */

import { useMemo } from 'react';
import {
  useQuery,
  useMutation,
  useQueryClient,
  useInfiniteQuery,
  type InfiniteData
} from '@tanstack/react-query';
import {
  getNotifications,
  getNotificationById,
  markAsRead,
  markAllAsRead,
  deleteNotification,
  bulkDismiss,
  getUnreadCount,
  getSettings,
  updateSettings,
  snoozeNotification
} from '../api';
import type {
  Notification,
  NotificationsResponse,
  NotificationSettings,
  NotificationSettingsUpdate,
  NotificationFilter,
  NotificationGroup,
  BulkDismissPayload
} from '../types';

/**
 * Query Keys
 */
export const notificationKeys = {
  all: ['notifications'] as const,
  lists: () => [...notificationKeys.all, 'list'] as const,
  list: (filter?: NotificationFilter) =>
    [...notificationKeys.lists(), filter] as const,
  details: () => [...notificationKeys.all, 'detail'] as const,
  detail: (id: string) => [...notificationKeys.details(), id] as const,
  unreadCount: () => [...notificationKeys.all, 'unread-count'] as const,
  settings: () => [...notificationKeys.all, 'settings'] as const
};

/**
 * Hook für Benachrichtigungen mit Infinite Scroll
 */
export function useNotifications(filter?: NotificationFilter) {
  return useInfiniteQuery({
    queryKey: notificationKeys.list(filter),
    queryFn: ({ pageParam = 1 }) =>
      getNotifications({ page: pageParam, page_size: 20, filter }),
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.page + 1 : undefined,
    initialPageParam: 1,
    staleTime: 1000 * 60 // 1 Minute
  });
}

/**
 * Hook für einzelne Benachrichtigung
 */
export function useNotification(id: string) {
  return useQuery({
    queryKey: notificationKeys.detail(id),
    queryFn: () => getNotificationById(id),
    enabled: !!id
  });
}

/**
 * Hook für Unread Count
 */
export function useUnreadCount() {
  return useQuery({
    queryKey: notificationKeys.unreadCount(),
    queryFn: getUnreadCount,
    refetchInterval: 1000 * 60, // Jede Minute aktualisieren
    staleTime: 1000 * 30 // 30 Sekunden
  });
}

/**
 * Hook für Mark as Read
 */
export function useMarkAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: markAsRead,
    onMutate: async (id) => {
      // Optimistic Update
      await queryClient.cancelQueries({ queryKey: notificationKeys.lists() });

      const previousData = queryClient.getQueriesData<
        InfiniteData<NotificationsResponse>
      >({
        queryKey: notificationKeys.lists()
      });

      // Update alle Listen
      queryClient.setQueriesData<InfiniteData<NotificationsResponse>>(
        { queryKey: notificationKeys.lists() },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              items: page.items.map((item) =>
                item.id === id ? { ...item, read: true } : item
              )
            }))
          };
        }
      );

      // Update Unread Count
      queryClient.setQueryData<number>(
        notificationKeys.unreadCount(),
        (old) => (old && old > 0 ? old - 1 : 0)
      );

      return { previousData };
    },
    onError: (_err, _variables, context) => {
      // Rollback bei Fehler
      if (context?.previousData) {
        context.previousData.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: notificationKeys.unreadCount()
      });
    }
  });
}

/**
 * Hook für Mark All as Read
 */
export function useMarkAllAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: markAllAsRead,
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: notificationKeys.lists() });

      const previousData = queryClient.getQueriesData<
        InfiniteData<NotificationsResponse>
      >({
        queryKey: notificationKeys.lists()
      });

      // Alle als gelesen markieren
      queryClient.setQueriesData<InfiniteData<NotificationsResponse>>(
        { queryKey: notificationKeys.lists() },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              items: page.items.map((item) => ({ ...item, read: true }))
            }))
          };
        }
      );

      // Unread Count auf 0 setzen
      queryClient.setQueryData(notificationKeys.unreadCount(), 0);

      return { previousData };
    },
    onError: (_err, _variables, context) => {
      if (context?.previousData) {
        context.previousData.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: notificationKeys.unreadCount()
      });
    }
  });
}

/**
 * Hook für Delete Notification
 */
export function useDeleteNotification() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteNotification,
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: notificationKeys.lists() });

      const previousData = queryClient.getQueriesData<
        InfiniteData<NotificationsResponse>
      >({
        queryKey: notificationKeys.lists()
      });

      // Benachrichtigung aus allen Listen entfernen
      queryClient.setQueriesData<InfiniteData<NotificationsResponse>>(
        { queryKey: notificationKeys.lists() },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              items: page.items.filter((item) => item.id !== id),
              total: page.total - 1
            }))
          };
        }
      );

      // Unread Count aktualisieren (falls ungelesen)
      const notification = queryClient
        .getQueriesData<InfiniteData<NotificationsResponse>>({
          queryKey: notificationKeys.lists()
        })[0]?.[1]
        ?.pages.flatMap((p) => p.items)
        .find((n) => n.id === id);

      if (notification && !notification.read) {
        queryClient.setQueryData<number>(
          notificationKeys.unreadCount(),
          (old) => (old && old > 0 ? old - 1 : 0)
        );
      }

      return { previousData };
    },
    onError: (_err, _variables, context) => {
      if (context?.previousData) {
        context.previousData.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: notificationKeys.unreadCount()
      });
    }
  });
}

/**
 * Hook für Bulk Dismiss
 */
export function useBulkDismiss() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: bulkDismiss,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: notificationKeys.unreadCount()
      });
    }
  });
}

/**
 * Hook für Notification Settings
 */
export function useNotificationSettings() {
  return useQuery({
    queryKey: notificationKeys.settings(),
    queryFn: getSettings,
    staleTime: 1000 * 60 * 5 // 5 Minuten
  });
}

/**
 * Hook für Update Settings
 */
export function useUpdateSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: updateSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(notificationKeys.settings(), data);
    }
  });
}

/**
 * Hook fuer Notification Snooze
 */
export function useSnoozeNotification() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, until }: { id: string; until: string }) =>
      snoozeNotification(id, until),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.lists() });
      queryClient.invalidateQueries({ queryKey: notificationKeys.unreadCount() });
    },
  });
}

/**
 * Hook fuer gruppierte Benachrichtigungen (client-side)
 */
export function useGroupedNotifications(notifications: Notification[]): NotificationGroup[] {
  return useMemo(() => {
    const groups = new Map<string, Notification[]>();
    const ungrouped: Notification[] = [];

    for (const n of notifications) {
      if (n.group_key) {
        const existing = groups.get(n.group_key) || [];
        groups.set(n.group_key, [...existing, n]);
      } else {
        ungrouped.push(n);
      }
    }

    const result: NotificationGroup[] = [];

    for (const [group_key, items] of groups.entries()) {
      const sorted = items.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      result.push({
        group_key,
        count: sorted.length,
        latest: sorted[0],
        notifications: sorted,
      });
    }

    // Nicht-gruppierte als einzelne Gruppen hinzufuegen
    for (const n of ungrouped) {
      result.push({
        group_key: n.id,
        count: 1,
        latest: n,
        notifications: [n],
      });
    }

    // Alle Gruppen nach neuestem Datum sortieren
    result.sort(
      (a, b) => new Date(b.latest.created_at).getTime() - new Date(a.latest.created_at).getTime()
    );

    return result;
  }, [notifications]);
}
