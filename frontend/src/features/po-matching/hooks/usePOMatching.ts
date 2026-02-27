/**
 * PO-Matching Query Hooks
 *
 * TanStack Query Hooks für 3-Way Purchase Order Matching.
 * Konsistente Query-Keys und wiederverwendbare Hooks.
 *
 * Features:
 * - Differenzierte Stale-Times
 * - Query-Key-Factory
 * - Mutations mit automatischer Invalidierung
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchPOMatches,
  fetchPOMatch,
  fetchPOMatchStats,
  triggerAutoMatch,
  approvePOMatch,
  evaluatePOMatch,
} from '../api/po-matching-api';
import { QUERY_VOLATILE, QUERY_STANDARD, QUERY_KPIS } from '@/lib/api/query-config';
import type { POMatchFilter } from '../types/po-matching-types';

// ==================== Konfiguration ====================

const STALE_TIMES = {
  list: QUERY_VOLATILE.staleTime,    // 30s - Liste kann sich schnell ändern
  detail: QUERY_STANDARD.staleTime,  // 60s - Detail ändert sich seltener
  stats: QUERY_KPIS.staleTime,       // 60s - Statistiken
} as const;

const GC_TIMES = {
  list: QUERY_VOLATILE.gcTime,       // 5min
  detail: QUERY_STANDARD.gcTime,     // 10min
  stats: QUERY_KPIS.gcTime,          // 10min
} as const;

// ==================== Query Keys ====================

export const poMatchKeys = {
  all: ['po-matches'] as const,
  list: (filters: POMatchFilter) =>
    [...poMatchKeys.all, 'list', filters] as const,
  detail: (id: string) =>
    [...poMatchKeys.all, 'detail', id] as const,
  stats: (start: string, end: string) =>
    [...poMatchKeys.all, 'stats', start, end] as const,
};

// ==================== Query Hooks ====================

/**
 * PO-Matches mit Filtern und Paginierung abrufen.
 */
export function usePOMatches(
  filters: POMatchFilter = {},
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: poMatchKeys.list(filters),
    queryFn: () => fetchPOMatches(filters),
    staleTime: STALE_TIMES.list,
    gcTime: GC_TIMES.list,
    enabled: options?.enabled !== false,
    placeholderData: (previousData) => previousData,
  });
}

/**
 * Einzelnen PO-Match mit Abweichungen abrufen.
 */
export function usePOMatch(
  matchId: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: poMatchKeys.detail(matchId),
    queryFn: () => fetchPOMatch(matchId),
    staleTime: STALE_TIMES.detail,
    gcTime: GC_TIMES.detail,
    enabled: options?.enabled !== false && !!matchId,
  });
}

/**
 * PO-Matching Statistiken für einen Zeitraum abrufen.
 */
export function usePOMatchStats(
  periodStart: string,
  periodEnd: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: poMatchKeys.stats(periodStart, periodEnd),
    queryFn: () => fetchPOMatchStats(periodStart, periodEnd),
    staleTime: STALE_TIMES.stats,
    gcTime: GC_TIMES.stats,
    enabled: options?.enabled !== false && !!periodStart && !!periodEnd,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Auto-Matching ausführen.
 */
export function useAutoMatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => triggerAutoMatch(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: poMatchKeys.all });
    },
  });
}

/**
 * Match freigeben.
 */
export function useApprovePOMatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      matchId,
      notes,
    }: {
      matchId: string;
      notes?: string;
    }) => approvePOMatch(matchId, notes),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: poMatchKeys.detail(variables.matchId),
      });
      queryClient.invalidateQueries({ queryKey: poMatchKeys.all });
    },
  });
}

/**
 * Match bewerten und Abweichungen erkennen.
 */
export function useEvaluatePOMatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (matchId: string) => evaluatePOMatch(matchId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: poMatchKeys.detail(data.id),
      });
      queryClient.invalidateQueries({ queryKey: poMatchKeys.all });
    },
  });
}
