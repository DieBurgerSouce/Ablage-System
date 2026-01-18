/**
 * Predictive Actions Hooks
 *
 * TanStack Query Hooks fuer proaktive Handlungsvorschlaege
 *
 * Features:
 * - Aktionen abrufen (kritisch, skonto, mahnung)
 * - Aktionen akzeptieren/ablehnen/verschieben
 * - Statistiken und Feedback
 *
 * Phase 2.2 der Feature-Roadmap (Januar 2026)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  predictiveActionsService,
  type PredictiveActionsFilter,
  type AcceptActionRequest,
  type RejectActionRequest,
  type SnoozeActionRequest,
  type PredictiveActionsListResponse,
  type ActionResult,
  type ActionStatistics,
  type ActionTypesResponse,
} from '@/lib/api/services/predictive-actions';

// ==================== Query Keys ====================

export const predictiveActionsQueryKeys = {
  all: ['predictive-actions'] as const,

  // Lists
  lists: () => [...predictiveActionsQueryKeys.all, 'list'] as const,
  list: (filter?: PredictiveActionsFilter) =>
    [...predictiveActionsQueryKeys.lists(), filter] as const,
  critical: (limit?: number) =>
    [...predictiveActionsQueryKeys.all, 'critical', limit] as const,
  skonto: (limit?: number) =>
    [...predictiveActionsQueryKeys.all, 'skonto', limit] as const,
  dunning: (limit?: number) =>
    [...predictiveActionsQueryKeys.all, 'dunning', limit] as const,

  // Statistics
  statistics: () => [...predictiveActionsQueryKeys.all, 'statistics'] as const,
  statisticsByDays: (days: number) =>
    [...predictiveActionsQueryKeys.statistics(), days] as const,

  // Types
  types: () => [...predictiveActionsQueryKeys.all, 'types'] as const,
};

// ==================== Stale Times ====================

const STALE_TIMES = {
  actions: 1000 * 60 * 2, // 2 Minuten
  critical: 1000 * 30, // 30 Sekunden (haeufiger aktualisieren)
  statistics: 1000 * 60 * 5, // 5 Minuten
  types: 1000 * 60 * 30, // 30 Minuten (selten aendernd)
};

// ==================== Query Hooks ====================

/**
 * Holt alle Aktionsvorschlaege
 */
export function usePredictiveActions(filter?: PredictiveActionsFilter) {
  return useQuery({
    queryKey: predictiveActionsQueryKeys.list(filter),
    queryFn: () => predictiveActionsService.getActions(filter),
    staleTime: STALE_TIMES.actions,
  });
}

/**
 * Holt kritische Aktionen (fuer Dashboard)
 */
export function useCriticalActions(limit = 10) {
  return useQuery({
    queryKey: predictiveActionsQueryKeys.critical(limit),
    queryFn: () => predictiveActionsService.getCriticalActions(limit),
    staleTime: STALE_TIMES.critical,
    refetchInterval: 1000 * 60, // Alle 60 Sekunden refetchen
  });
}

/**
 * Holt Skonto-spezifische Vorschlaege
 */
export function useSkontoActions(limit = 20) {
  return useQuery({
    queryKey: predictiveActionsQueryKeys.skonto(limit),
    queryFn: () => predictiveActionsService.getSkontoActions(limit),
    staleTime: STALE_TIMES.actions,
  });
}

/**
 * Holt Mahnungs-spezifische Vorschlaege
 */
export function useDunningActions(limit = 20) {
  return useQuery({
    queryKey: predictiveActionsQueryKeys.dunning(limit),
    queryFn: () => predictiveActionsService.getDunningActions(limit),
    staleTime: STALE_TIMES.actions,
  });
}

/**
 * Holt Statistiken zu Aktionsvorschlaegen
 */
export function useActionStatistics(days = 30) {
  return useQuery({
    queryKey: predictiveActionsQueryKeys.statisticsByDays(days),
    queryFn: () => predictiveActionsService.getStatistics(days),
    staleTime: STALE_TIMES.statistics,
  });
}

/**
 * Holt verfuegbare Aktionstypen
 */
export function useActionTypes() {
  return useQuery({
    queryKey: predictiveActionsQueryKeys.types(),
    queryFn: () => predictiveActionsService.getActionTypes(),
    staleTime: STALE_TIMES.types,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Aktion akzeptieren
 */
export function useAcceptAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      actionId,
      request = {},
    }: {
      actionId: string;
      request?: AcceptActionRequest;
    }) => predictiveActionsService.acceptAction(actionId, request),
    onSuccess: () => {
      // Invalidiere alle relevanten Queries
      queryClient.invalidateQueries({
        queryKey: predictiveActionsQueryKeys.all,
      });
    },
  });
}

/**
 * Aktion ablehnen
 */
export function useRejectAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      actionId,
      request = {},
    }: {
      actionId: string;
      request?: RejectActionRequest;
    }) => predictiveActionsService.rejectAction(actionId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: predictiveActionsQueryKeys.all,
      });
    },
  });
}

/**
 * Aktion verschieben (snooze)
 */
export function useSnoozeAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      actionId,
      request = {},
    }: {
      actionId: string;
      request?: SnoozeActionRequest;
    }) => predictiveActionsService.snoozeAction(actionId, request),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: predictiveActionsQueryKeys.all,
      });
    },
  });
}

// ==================== Utility Hooks ====================

/**
 * Invalidiert alle Predictive Actions Queries
 */
export function useInvalidatePredictiveActionsQueries() {
  const queryClient = useQueryClient();

  return {
    invalidateAll: () => {
      queryClient.invalidateQueries({
        queryKey: predictiveActionsQueryKeys.all,
      });
    },
    invalidateLists: () => {
      queryClient.invalidateQueries({
        queryKey: predictiveActionsQueryKeys.lists(),
      });
    },
    invalidateCritical: () => {
      queryClient.invalidateQueries({
        queryKey: [...predictiveActionsQueryKeys.all, 'critical'],
      });
    },
    invalidateSkonto: () => {
      queryClient.invalidateQueries({
        queryKey: [...predictiveActionsQueryKeys.all, 'skonto'],
      });
    },
    invalidateDunning: () => {
      queryClient.invalidateQueries({
        queryKey: [...predictiveActionsQueryKeys.all, 'dunning'],
      });
    },
    invalidateStatistics: () => {
      queryClient.invalidateQueries({
        queryKey: predictiveActionsQueryKeys.statistics(),
      });
    },
  };
}

/**
 * Prefetch kritische Aktionen fuer schnellere Darstellung
 */
export function usePrefetchCriticalActions() {
  const queryClient = useQueryClient();

  return (limit = 10) => {
    queryClient.prefetchQuery({
      queryKey: predictiveActionsQueryKeys.critical(limit),
      queryFn: () => predictiveActionsService.getCriticalActions(limit),
      staleTime: STALE_TIMES.critical,
    });
  };
}
