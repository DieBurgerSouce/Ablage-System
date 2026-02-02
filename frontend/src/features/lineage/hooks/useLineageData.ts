/**
 * useLineageData Hook
 *
 * React Query Hook fuer den Abruf von Dokumenten-Lineage-Daten.
 * Kombiniert Timeline, Statistiken und Zusammenfassung.
 */

import { useQuery, useQueries } from '@tanstack/react-query';
import {
  lineageService,
  type LineageEventType,
  type TimelineResponse,
  type LineageStats,
  type LineageSummary,
  type EventTypeLabels,
} from '@/lib/api/services/lineage';

// =============================================================================
// Query Keys
// =============================================================================

export const lineageQueryKeys = {
  all: ['lineage'] as const,
  timeline: (documentId: string) => [...lineageQueryKeys.all, 'timeline', documentId] as const,
  stats: (documentId: string) => [...lineageQueryKeys.all, 'stats', documentId] as const,
  summary: (documentId: string) => [...lineageQueryKeys.all, 'summary', documentId] as const,
  eventTypes: () => [...lineageQueryKeys.all, 'eventTypes'] as const,
  importSourceTypes: () => [...lineageQueryKeys.all, 'importSourceTypes'] as const,
};

// =============================================================================
// Individual Hooks
// =============================================================================

export interface UseTimelineOptions {
  limit?: number;
  offset?: number;
  eventTypes?: LineageEventType[];
  enabled?: boolean;
}

/**
 * Ruft die Lineage-Timeline eines Dokuments ab.
 */
export function useLineageTimeline(
  documentId: string,
  options?: UseTimelineOptions
) {
  const { limit, offset, eventTypes, enabled = true } = options ?? {};

  return useQuery({
    queryKey: [
      ...lineageQueryKeys.timeline(documentId),
      { limit, offset, eventTypes },
    ],
    queryFn: () =>
      lineageService.getTimeline(documentId, { limit, offset, eventTypes }),
    enabled: enabled && !!documentId,
    staleTime: 30_000, // 30 Sekunden
    refetchOnWindowFocus: false,
  });
}

/**
 * Ruft die Lineage-Statistiken eines Dokuments ab.
 */
export function useLineageStats(documentId: string, enabled = true) {
  return useQuery({
    queryKey: lineageQueryKeys.stats(documentId),
    queryFn: () => lineageService.getStats(documentId),
    enabled: enabled && !!documentId,
    staleTime: 60_000, // 1 Minute
    refetchOnWindowFocus: false,
  });
}

/**
 * Ruft die Lineage-Zusammenfassung eines Dokuments ab.
 */
export function useLineageSummary(documentId: string, enabled = true) {
  return useQuery({
    queryKey: lineageQueryKeys.summary(documentId),
    queryFn: () => lineageService.getSummary(documentId),
    enabled: enabled && !!documentId,
    staleTime: 60_000, // 1 Minute
    refetchOnWindowFocus: false,
  });
}

/**
 * Ruft alle verfuegbaren Event-Typen ab.
 */
export function useEventTypes() {
  return useQuery({
    queryKey: lineageQueryKeys.eventTypes(),
    queryFn: () => lineageService.getEventTypes(),
    staleTime: 24 * 60 * 60 * 1000, // 24 Stunden (statische Daten)
    refetchOnWindowFocus: false,
  });
}

/**
 * Ruft alle verfuegbaren Import-Quelltypen ab.
 */
export function useImportSourceTypes() {
  return useQuery({
    queryKey: lineageQueryKeys.importSourceTypes(),
    queryFn: () => lineageService.getImportSourceTypes(),
    staleTime: 24 * 60 * 60 * 1000, // 24 Stunden (statische Daten)
    refetchOnWindowFocus: false,
  });
}

// =============================================================================
// Combined Hook
// =============================================================================

export interface UseLineageDataResult {
  timeline: TimelineResponse | undefined;
  stats: LineageStats | undefined;
  summary: LineageSummary | undefined;
  eventTypeLabels: EventTypeLabels | undefined;
  importSourceLabels: Record<string, string> | undefined;
  isLoading: boolean;
  isError: boolean;
  errors: (Error | null)[];
  refetch: () => void;
}

/**
 * Kombinierter Hook fuer alle Lineage-Daten eines Dokuments.
 */
export function useLineageData(
  documentId: string,
  options?: UseTimelineOptions
): UseLineageDataResult {
  const { limit, offset, eventTypes, enabled = true } = options ?? {};

  const results = useQueries({
    queries: [
      {
        queryKey: [
          ...lineageQueryKeys.timeline(documentId),
          { limit, offset, eventTypes },
        ],
        queryFn: () =>
          lineageService.getTimeline(documentId, { limit, offset, eventTypes }),
        enabled: enabled && !!documentId,
        staleTime: 30_000,
      },
      {
        queryKey: lineageQueryKeys.stats(documentId),
        queryFn: () => lineageService.getStats(documentId),
        enabled: enabled && !!documentId,
        staleTime: 60_000,
      },
      {
        queryKey: lineageQueryKeys.summary(documentId),
        queryFn: () => lineageService.getSummary(documentId),
        enabled: enabled && !!documentId,
        staleTime: 60_000,
      },
      {
        queryKey: lineageQueryKeys.eventTypes(),
        queryFn: () => lineageService.getEventTypes(),
        staleTime: 24 * 60 * 60 * 1000,
      },
      {
        queryKey: lineageQueryKeys.importSourceTypes(),
        queryFn: () => lineageService.getImportSourceTypes(),
        staleTime: 24 * 60 * 60 * 1000,
      },
    ],
  });

  const isLoading = results.some((r) => r.isLoading);
  const isError = results.some((r) => r.isError);
  const errors = results.map((r) => r.error);

  const refetch = () => {
    results.forEach((r) => r.refetch());
  };

  return {
    timeline: results[0].data as TimelineResponse | undefined,
    stats: results[1].data as LineageStats | undefined,
    summary: results[2].data as LineageSummary | undefined,
    eventTypeLabels: results[3].data as EventTypeLabels | undefined,
    importSourceLabels: results[4].data as Record<string, string> | undefined,
    isLoading,
    isError,
    errors,
    refetch,
  };
}
