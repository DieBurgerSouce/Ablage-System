/**
 * Shipment Query Hooks
 *
 * TanStack Query Hooks für Sendungsverfolgung.
 * Konsistente Query-Keys und wiederverwendbare Hooks.
 *
 * Features:
 * - Differenzierte Stale-Times
 * - Optimistic Updates für bessere UX
 * - Error Retry mit Backoff
 */

import { useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { shipmentService, ShipmentApiError } from '../api/shipment-api';
import { QUERY_VOLATILE, QUERY_STANDARD, QUERY_SEMI_STATIC, QUERY_STATIC } from '@/lib/api/query-config';
import type {
  ShipmentFilter,
  ShipmentCreate,
  ShipmentUpdate,
  ShipmentResponse,
} from '../types/shipment-types';

// ==================== Konfiguration ====================

const STALE_TIMES = {
  shipments: QUERY_STANDARD.staleTime,     // 60s - Tracking-Status kann sich ändern
  summary: QUERY_STANDARD.staleTime,       // 60s - Zusammenfassung
  statistics: QUERY_SEMI_STATIC.staleTime, // 5min - Statistiken ändern sich selten
  detail: QUERY_VOLATILE.staleTime,        // 30s - Detail soll aktuell sein
  carriers: QUERY_STATIC.staleTime,        // 1h - Carrier-Liste ändert sich nie
} as const;

const GC_TIMES = {
  shipments: QUERY_STANDARD.gcTime,        // 10min
  summary: QUERY_STANDARD.gcTime,          // 10min
  statistics: QUERY_SEMI_STATIC.gcTime,    // 30min
  detail: QUERY_VOLATILE.gcTime,           // 5min
  carriers: QUERY_STATIC.gcTime,           // 2h
} as const;

const RETRY_CONFIG = {
  retry: (failureCount: number, error: unknown) => {
    // Keine Retries bei 4xx Fehlern (Client-Fehler)
    if (error instanceof ShipmentApiError && error.statusCode) {
      if (error.statusCode >= 400 && error.statusCode < 500) {
        return false;
      }
    }
    // Maximal 3 Retries bei Server-Fehlern
    return failureCount < 3;
  },
  retryDelay: (attemptIndex: number) => Math.min(1000 * 2 ** attemptIndex, 30000),
} as const;

// ==================== Query Keys ====================

export const shipmentQueryKeys = {
  all: ['shipments'] as const,

  // Sendungsliste
  list: () => [...shipmentQueryKeys.all, 'list'] as const,
  listFiltered: (filter: Partial<ShipmentFilter>) =>
    [...shipmentQueryKeys.list(), filter] as const,

  // Zusammenfassung
  summary: () => [...shipmentQueryKeys.all, 'summary'] as const,

  // Statistiken
  statistics: (days?: number) =>
    [...shipmentQueryKeys.all, 'statistics', days ?? 90] as const,

  // Einzelne Sendung
  detail: (id: string) => [...shipmentQueryKeys.all, 'detail', id] as const,

  // Carrier
  carriers: () => [...shipmentQueryKeys.all, 'carriers'] as const,
};

// ==================== Query Hooks ====================

/**
 * Sendungen mit Filter und Pagination abrufen
 */
export function useShipments(
  filter: Partial<ShipmentFilter> = {},
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: shipmentQueryKeys.listFiltered(filter),
    queryFn: () => shipmentService.listShipments(filter),
    staleTime: STALE_TIMES.shipments,
    gcTime: GC_TIMES.shipments,
    enabled: options?.enabled !== false,
    placeholderData: (previousData) => previousData,
    ...RETRY_CONFIG,
  });
}

/**
 * Sendungs-Zusammenfassung abrufen
 */
export function useShipmentSummary(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: shipmentQueryKeys.summary(),
    queryFn: () => shipmentService.getSummary(),
    staleTime: STALE_TIMES.summary,
    gcTime: GC_TIMES.summary,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

/**
 * Carrier-Statistiken abrufen
 */
export function useCarrierStatistics(
  days: number = 90,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: shipmentQueryKeys.statistics(days),
    queryFn: () => shipmentService.getStatistics(days),
    staleTime: STALE_TIMES.statistics,
    gcTime: GC_TIMES.statistics,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

/**
 * Einzelne Sendung abrufen
 */
export function useShipment(shipmentId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: shipmentQueryKeys.detail(shipmentId),
    queryFn: () => shipmentService.getShipment(shipmentId),
    staleTime: STALE_TIMES.detail,
    gcTime: GC_TIMES.detail,
    enabled: options?.enabled !== false && !!shipmentId,
    ...RETRY_CONFIG,
  });
}

/**
 * Carrier-Liste abrufen
 */
export function useCarriers(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: shipmentQueryKeys.carriers(),
    queryFn: () => shipmentService.listCarriers(),
    staleTime: STALE_TIMES.carriers,
    gcTime: GC_TIMES.carriers,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Sendung erstellen
 */
export function useCreateShipment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ShipmentCreate) =>
      shipmentService.createShipment(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: shipmentQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: shipmentQueryKeys.summary() });
    },
  });
}

/**
 * Sendung aktualisieren
 */
export function useUpdateShipment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      shipmentId,
      data,
    }: {
      shipmentId: string;
      data: ShipmentUpdate;
    }) => shipmentService.updateShipment(shipmentId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: shipmentQueryKeys.detail(variables.shipmentId),
      });
      queryClient.invalidateQueries({ queryKey: shipmentQueryKeys.list() });
    },
  });
}

/**
 * Sendung löschen
 */
export function useDeleteShipment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (shipmentId: string) => shipmentService.deleteShipment(shipmentId),
    onSuccess: (_, shipmentId) => {
      queryClient.invalidateQueries({
        queryKey: shipmentQueryKeys.detail(shipmentId),
      });
      queryClient.invalidateQueries({ queryKey: shipmentQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: shipmentQueryKeys.summary() });
    },
  });
}

/**
 * Tracking einer Sendung aktualisieren
 */
export function useRefreshTracking() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (shipmentId: string) => shipmentService.refreshTracking(shipmentId),
    onSuccess: (updatedShipment) => {
      // Aktualisiere Detail-Cache direkt
      queryClient.setQueryData(
        shipmentQueryKeys.detail(updatedShipment.id),
        updatedShipment
      );
      queryClient.invalidateQueries({ queryKey: shipmentQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: shipmentQueryKeys.summary() });
    },
  });
}

/**
 * Alle aktiven Sendungen aktualisieren
 */
export function useRefreshAllShipments() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => shipmentService.refreshAllActive(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: shipmentQueryKeys.all });
    },
  });
}

/**
 * Carrier erkennen
 */
export function useDetectCarrier() {
  return useMutation({
    mutationFn: (trackingNumber: string) =>
      shipmentService.detectCarrier(trackingNumber),
  });
}

// ==================== Combined Hooks ====================

/**
 * Kombinierter Hook für Sendungs-Übersichtsseite
 * Lädt Sendungen, Zusammenfassung und Statistiken
 */
export function useShipmentPage(
  filter: Partial<ShipmentFilter> = {},
  options?: { enabled?: boolean }
) {
  const isEnabled = options?.enabled !== false;

  const shipmentsQuery = useShipments(filter, { enabled: isEnabled });
  const summaryQuery = useShipmentSummary({ enabled: isEnabled });
  const statisticsQuery = useCarrierStatistics(90, { enabled: isEnabled });

  return {
    // Daten
    shipments: shipmentsQuery.data?.items ?? [],
    pagination: shipmentsQuery.data
      ? {
          total: shipmentsQuery.data.total,
          page: shipmentsQuery.data.page,
          perPage: shipmentsQuery.data.perPage,
          pages: shipmentsQuery.data.pages,
        }
      : null,
    summary: summaryQuery.data,
    statistics: statisticsQuery.data ?? [],

    // Ladezustand
    isLoading:
      shipmentsQuery.isLoading ||
      summaryQuery.isLoading ||
      statisticsQuery.isLoading,
    isLoadingShipments: shipmentsQuery.isLoading,
    isLoadingSummary: summaryQuery.isLoading,
    isLoadingStatistics: statisticsQuery.isLoading,
    isFetching:
      shipmentsQuery.isFetching ||
      summaryQuery.isFetching ||
      statisticsQuery.isFetching,

    // Fehlerzustand
    isError:
      shipmentsQuery.isError ||
      summaryQuery.isError ||
      statisticsQuery.isError,
    error: shipmentsQuery.error || summaryQuery.error || statisticsQuery.error,

    // Aktionen
    refetch: () => {
      shipmentsQuery.refetch();
      summaryQuery.refetch();
      statisticsQuery.refetch();
    },
  };
}

/**
 * Kombinierter Hook für alle Sendungs-Mutationen
 */
export function useShipmentMutations() {
  const createShipment = useCreateShipment();
  const updateShipment = useUpdateShipment();
  const deleteShipment = useDeleteShipment();
  const refreshTracking = useRefreshTracking();
  const refreshAll = useRefreshAllShipments();

  const isAnyMutating =
    createShipment.isPending ||
    updateShipment.isPending ||
    deleteShipment.isPending ||
    refreshTracking.isPending ||
    refreshAll.isPending;

  return {
    // Mutations
    createShipment,
    updateShipment,
    deleteShipment,
    refreshTracking,
    refreshAll,

    // Status
    isAnyMutating,
  };
}

// ==================== Prefetch Helpers ====================

/**
 * Prefetch für Sendungsliste
 */
export function usePrefetchShipments() {
  const queryClient = useQueryClient();

  const prefetch = useCallback(
    (filter: Partial<ShipmentFilter> = {}) => {
      queryClient.prefetchQuery({
        queryKey: shipmentQueryKeys.listFiltered(filter),
        queryFn: () => shipmentService.listShipments(filter),
        staleTime: STALE_TIMES.shipments,
      });
    },
    [queryClient]
  );

  return prefetch;
}

/**
 * Prefetch für Sendungsdetail
 */
export function usePrefetchShipment() {
  const queryClient = useQueryClient();

  const prefetch = useCallback(
    (shipmentId: string) => {
      queryClient.prefetchQuery({
        queryKey: shipmentQueryKeys.detail(shipmentId),
        queryFn: () => shipmentService.getShipment(shipmentId),
        staleTime: STALE_TIMES.detail,
      });
    },
    [queryClient]
  );

  return prefetch;
}

// ==================== Utility Helpers ====================

/**
 * Invalidiert alle Sendungs-relevanten Queries
 */
export function useInvalidateShipmentQueries() {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: shipmentQueryKeys.all });
  }, [queryClient]);
}
