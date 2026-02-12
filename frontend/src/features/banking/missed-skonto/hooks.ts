/**
 * Missed Skonto Hooks
 * TanStack Query Hooks für verpasste Skonto-Daten
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import {
  getMissedSkonto,
  getSkontoStatistics,
  getMonthlySkontoSummary,
  exportMissedSkonto,
} from './api';
import type { MissedSkontoFilters } from './types';

// Query Keys
export const missedSkontoKeys = {
  all: ['missed-skonto'] as const,
  list: (filters?: MissedSkontoFilters) =>
    [...missedSkontoKeys.all, 'list', filters] as const,
  statistics: (startDate: string, endDate: string) =>
    [...missedSkontoKeys.all, 'statistics', startDate, endDate] as const,
  monthly: (months: number) =>
    [...missedSkontoKeys.all, 'monthly', months] as const,
};

// Stale times
const STALE_TIMES = {
  list: 2 * 60 * 1000, // 2 Minuten
  statistics: 5 * 60 * 1000, // 5 Minuten
  monthly: 10 * 60 * 1000, // 10 Minuten
};

/**
 * Verpasste Skonto-Liste abrufen
 */
export function useMissedSkonto(filters: MissedSkontoFilters = {}) {
  return useQuery({
    queryKey: missedSkontoKeys.list(filters),
    queryFn: () => getMissedSkonto(filters),
    staleTime: STALE_TIMES.list,
  });
}

/**
 * Skonto-Statistiken abrufen
 */
export function useSkontoStatistics(startDate: string, endDate: string, enabled = true) {
  return useQuery({
    queryKey: missedSkontoKeys.statistics(startDate, endDate),
    queryFn: () => getSkontoStatistics(startDate, endDate),
    staleTime: STALE_TIMES.statistics,
    enabled: enabled && !!startDate && !!endDate,
  });
}

/**
 * Monatliche Zusammenfassung abrufen
 */
export function useMonthlySkontoSummary(months: number = 12) {
  return useQuery({
    queryKey: missedSkontoKeys.monthly(months),
    queryFn: () => getMonthlySkontoSummary(months),
    staleTime: STALE_TIMES.monthly,
  });
}

/**
 * Export-Mutation
 */
export function useExportMissedSkonto() {
  return useMutation({
    mutationFn: ({
      format,
      filters,
    }: {
      format: 'xlsx' | 'csv';
      filters?: MissedSkontoFilters;
    }) => exportMissedSkonto(format, filters),
    onSuccess: (blob, variables) => {
      // Trigger Download
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `verpasste-skonto-${new Date().toISOString().slice(0, 10)}.${variables.format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    },
  });
}
