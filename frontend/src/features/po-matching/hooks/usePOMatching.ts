/**
 * PO-Matching Query Hooks
 *
 * TanStack Query Hooks fuer 3-Way Purchase Order Matching.
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
import type { POMatchFilter } from '../types/po-matching-types';

// ==================== Konfiguration ====================

const STALE_TIMES = {
  list: 30 * 1000,        // 30 Sekunden - Liste kann sich schnell aendern
  detail: 60 * 1000,      // 1 Minute - Detail aendert sich seltener
  stats: 2 * 60 * 1000,   // 2 Minuten - Statistiken aendern sich selten
} as const;

const GC_TIMES = {
  list: 5 * 60 * 1000,     // 5 Minuten
  detail: 15 * 60 * 1000,  // 15 Minuten
  stats: 10 * 60 * 1000,   // 10 Minuten
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
 * PO-Matching Statistiken fuer einen Zeitraum abrufen.
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
 * Auto-Matching ausfuehren.
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
