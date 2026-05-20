/**
 * Smart Inbox Query Hooks
 *
 * TanStack Query Hooks für Smart Inbox Feature.
 */

import { useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRealtimeInvalidation } from '@/lib/websocket';
import {
  smartInboxService,
  SmartInboxApiError,
} from '../api/smart-inbox-api';
import { QUERY_VOLATILE, QUERY_STANDARD } from '@/lib/api/query-config';
import type {
  InboxFilter,
  InboxActionType,
} from '../types/smart-inbox-types';

// ==================== WebSocket Echtzeit-Integration ====================

/**
 * Hook fuer WebSocket-basierte Smart Inbox Invalidation.
 * Muss in einer Smart Inbox Komponente aufgerufen werden.
 */
export function useSmartInboxRealtime(): void {
  useRealtimeInvalidation('notification.received', [['smart-inbox']]);
  useRealtimeInvalidation('document.uploaded', [['smart-inbox']]);
  useRealtimeInvalidation('approval.requested', [['smart-inbox']]);
  useRealtimeInvalidation('import.completed', [['smart-inbox']]);
}

// ==================== Konfiguration ====================

const STALE_TIMES = {
  items: QUERY_VOLATILE.staleTime,         // 30s
  insights: QUERY_STANDARD.staleTime,      // 60s
  stats: QUERY_VOLATILE.staleTime,         // 30s
} as const;

const GC_TIMES = {
  items: QUERY_VOLATILE.gcTime,            // 5min
  insights: QUERY_STANDARD.gcTime,         // 10min
  stats: QUERY_VOLATILE.gcTime,            // 5min
} as const;

const RETRY_CONFIG = {
  retry: (failureCount: number, error: unknown) => {
    if (error instanceof SmartInboxApiError && error.statusCode) {
      if (error.statusCode >= 400 && error.statusCode < 500) {
        return false;
      }
    }
    return failureCount < 3;
  },
  retryDelay: (attemptIndex: number) => Math.min(1000 * 2 ** attemptIndex, 30000),
} as const;

// ==================== Query Keys ====================

export const smartInboxQueryKeys = {
  all: ['smart-inbox'] as const,
  items: (filter?: InboxFilter) => [...smartInboxQueryKeys.all, 'items', filter] as const,
  stats: () => [...smartInboxQueryKeys.all, 'stats'] as const,
  insights: () => [...smartInboxQueryKeys.all, 'insights'] as const,
};

// ==================== Inbox Items Hooks ====================

/**
 * Ruft priorisierte Inbox-Items ab
 * Automatisches Polling alle 30 Sekunden
 */
export function useSmartInboxItems(params?: InboxFilter, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: smartInboxQueryKeys.items(params),
    queryFn: () => smartInboxService.getItems(params),
    staleTime: STALE_TIMES.items,
    gcTime: GC_TIMES.items,
    refetchInterval: 30000, // Poll alle 30 Sekunden
    enabled: options?.enabled !== false,
    placeholderData: (previousData) => previousData,
    ...RETRY_CONFIG,
  });
}

/**
 * Ruft Inbox-Statistiken ab
 */
export function useSmartInboxStats(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: smartInboxQueryKeys.stats(),
    queryFn: () => smartInboxService.getStats(),
    staleTime: STALE_TIMES.stats,
    gcTime: GC_TIMES.stats,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

/**
 * Ruft AI-generierte Insights ab
 */
export function useSmartInboxInsights(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: smartInboxQueryKeys.insights(),
    queryFn: () => smartInboxService.getInsights(),
    staleTime: STALE_TIMES.insights,
    gcTime: GC_TIMES.insights,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Führt eine Action auf einem Inbox-Item aus
 */
export function usePerformInboxAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      itemId,
      action,
      data,
    }: {
      itemId: string;
      action: InboxActionType;
      data?: Record<string, unknown>;
    }) => smartInboxService.performAction(itemId, action, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: smartInboxQueryKeys.items() });
      queryClient.invalidateQueries({ queryKey: smartInboxQueryKeys.stats() });
    },
  });
}

/**
 * Snoozt ein Inbox-Item
 */
export function useSnoozeInboxItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      itemId,
      snoozeUntil,
    }: {
      itemId: string;
      snoozeUntil: string;
    }) => smartInboxService.snoozeItem(itemId, snoozeUntil),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: smartInboxQueryKeys.items() });
    },
  });
}

/**
 * Dismisst ein Inbox-Item
 */
export function useDismissInboxItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itemId: string) => smartInboxService.dismissItem(itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: smartInboxQueryKeys.items() });
      queryClient.invalidateQueries({ queryKey: smartInboxQueryKeys.stats() });
    },
  });
}

/**
 * Triggert manuelle Aggregation
 */
export function useTriggerAggregation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => smartInboxService.triggerAggregation(),
    onSuccess: () => {
      // Nach Aggregation alle Inbox-Daten neu laden
      queryClient.invalidateQueries({ queryKey: smartInboxQueryKeys.all });
    },
  });
}

// ==================== Combined Hooks ====================

/**
 * Kombinierter Hook für Smart Inbox Dashboard
 */
export function useSmartInboxDashboard(
  filter?: InboxFilter,
  options?: { enabled?: boolean }
) {
  const isEnabled = options?.enabled !== false;

  const itemsQuery = useSmartInboxItems(filter, { enabled: isEnabled });
  const statsQuery = useSmartInboxStats({ enabled: isEnabled });
  const insightsQuery = useSmartInboxInsights({ enabled: isEnabled });

  return {
    items: itemsQuery.data?.items ?? [],
    total: itemsQuery.data?.total ?? 0,
    hasMore: itemsQuery.data?.hasMore ?? false,
    stats: statsQuery.data,
    insights: insightsQuery.data?.insights ?? [],
    isLoading:
      itemsQuery.isLoading ||
      statsQuery.isLoading ||
      insightsQuery.isLoading,
    isError:
      itemsQuery.isError ||
      statsQuery.isError ||
      insightsQuery.isError,
    refetch: () => {
      itemsQuery.refetch();
      statsQuery.refetch();
      insightsQuery.refetch();
    },
  };
}

/**
 * Hook für alle Smart Inbox Mutationen
 */
export function useSmartInboxMutations() {
  const performAction = usePerformInboxAction();
  const snoozeItem = useSnoozeInboxItem();
  const dismissItem = useDismissInboxItem();
  const triggerAggregation = useTriggerAggregation();

  const isAnyMutating =
    performAction.isPending ||
    snoozeItem.isPending ||
    dismissItem.isPending ||
    triggerAggregation.isPending;

  return {
    performAction,
    snoozeItem,
    dismissItem,
    triggerAggregation,
    isAnyMutating,
  };
}

// ==================== Prefetch Helpers ====================

/**
 * Prefetch Inbox Items
 */
export function usePrefetchInboxItems() {
  const queryClient = useQueryClient();

  return useCallback(
    (filter?: InboxFilter) => {
      queryClient.prefetchQuery({
        queryKey: smartInboxQueryKeys.items(filter),
        queryFn: () => smartInboxService.getItems(filter),
        staleTime: STALE_TIMES.items,
      });
    },
    [queryClient]
  );
}

/**
 * Prefetch Stats
 */
export function usePrefetchInboxStats() {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.prefetchQuery({
      queryKey: smartInboxQueryKeys.stats(),
      queryFn: () => smartInboxService.getStats(),
      staleTime: STALE_TIMES.stats,
    });
  }, [queryClient]);
}

/**
 * Invalidiert alle Smart Inbox Queries
 */
export function useInvalidateSmartInboxQueries() {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: smartInboxQueryKeys.all });
  }, [queryClient]);
}
