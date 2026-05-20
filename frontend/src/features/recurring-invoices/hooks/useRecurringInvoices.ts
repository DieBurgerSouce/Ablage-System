/**
 * Recurring Invoice Query Hooks
 *
 * TanStack Query Hooks für Abo-Rechnungen.
 * Konsistente Query-Keys und wiederverwendbare Hooks.
 *
 * Features:
 * - Differenzierte Stale-Times
 * - Optimistic Updates für bessere UX
 * - Error Retry mit Backoff
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchRecurringInvoices,
  fetchRecurringInvoice,
  createRecurringInvoice,
  updateRecurringInvoice,
  detectPatterns,
  fetchMissingInvoices,
  fetchPriceChanges,
  fetchSollIstReport,
  manualMatchDocument,
} from '../api/recurring-api';
import { QUERY_VOLATILE, QUERY_STANDARD, QUERY_SEMI_STATIC, QUERY_KPIS } from '@/lib/api/query-config';
import type {
  RecurringInvoiceFilter,
  RecurringInvoiceCreate,
  RecurringInvoiceUpdate,
  DetectPatternsParams,
} from '../types/recurring-types';

// ==================== Konfiguration ====================

const STALE_TIMES = {
  list: QUERY_VOLATILE.staleTime,          // 30s
  detail: QUERY_SEMI_STATIC.staleTime,    // 5min
  alerts: QUERY_STANDARD.staleTime,        // 60s
  report: QUERY_KPIS.staleTime,            // 60s
} as const;

const GC_TIMES = {
  list: QUERY_VOLATILE.gcTime,             // 5min
  detail: QUERY_SEMI_STATIC.gcTime,       // 30min
  alerts: QUERY_STANDARD.gcTime,           // 10min
  report: QUERY_KPIS.gcTime,              // 10min
} as const;

// ==================== Query Keys ====================

export const recurringQueryKeys = {
  all: ['recurring-invoices'] as const,

  // Listen
  list: () => [...recurringQueryKeys.all, 'list'] as const,
  listFiltered: (filter: RecurringInvoiceFilter) =>
    [...recurringQueryKeys.list(), filter] as const,

  // Detail
  detail: (id: string) => [...recurringQueryKeys.all, 'detail', id] as const,

  // Alerts
  missing: () => [...recurringQueryKeys.all, 'missing'] as const,
  priceChanges: () => [...recurringQueryKeys.all, 'price-changes'] as const,

  // Soll/Ist
  sollIst: (year: number, month: number) =>
    [...recurringQueryKeys.all, 'soll-ist', year, month] as const,
};

// ==================== Query Hooks ====================

/**
 * Abo-Rechnungen mit Filter und Pagination abrufen
 */
export function useRecurringInvoices(
  filters: RecurringInvoiceFilter = {},
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: recurringQueryKeys.listFiltered(filters),
    queryFn: () => fetchRecurringInvoices(filters),
    staleTime: STALE_TIMES.list,
    gcTime: GC_TIMES.list,
    enabled: options?.enabled !== false,
    placeholderData: (previousData) => previousData,
  });
}

/**
 * Einzelne Abo-Rechnung mit Occurrences abrufen
 */
export function useRecurringInvoice(
  id: string,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: recurringQueryKeys.detail(id),
    queryFn: () => fetchRecurringInvoice(id),
    staleTime: STALE_TIMES.detail,
    gcTime: GC_TIMES.detail,
    enabled: options?.enabled !== false && !!id,
  });
}

/**
 * Fehlende Rechnungen abrufen
 */
export function useMissingInvoices(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: recurringQueryKeys.missing(),
    queryFn: () => fetchMissingInvoices(),
    staleTime: STALE_TIMES.alerts,
    gcTime: GC_TIMES.alerts,
    enabled: options?.enabled !== false,
  });
}

/**
 * Preisänderungen abrufen
 */
export function usePriceChanges(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: recurringQueryKeys.priceChanges(),
    queryFn: () => fetchPriceChanges(),
    staleTime: STALE_TIMES.alerts,
    gcTime: GC_TIMES.alerts,
    enabled: options?.enabled !== false,
  });
}

/**
 * Soll/Ist-Bericht abrufen
 */
export function useSollIstReport(
  year: number,
  month: number,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: recurringQueryKeys.sollIst(year, month),
    queryFn: () => fetchSollIstReport(year, month),
    staleTime: STALE_TIMES.report,
    gcTime: GC_TIMES.report,
    enabled: options?.enabled !== false && year > 0 && month >= 1 && month <= 12,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Muster erkennen (Mutation)
 */
export function useDetectPatterns() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params?: DetectPatternsParams) => detectPatterns(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: recurringQueryKeys.list() });
    },
  });
}

/**
 * Abo-Rechnung erstellen
 */
export function useCreateRecurring() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: RecurringInvoiceCreate) => createRecurringInvoice(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: recurringQueryKeys.list() });
    },
  });
}

/**
 * Abo-Rechnung aktualisieren
 */
export function useUpdateRecurring() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: RecurringInvoiceUpdate }) =>
      updateRecurringInvoice(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: recurringQueryKeys.detail(variables.id),
      });
      queryClient.invalidateQueries({ queryKey: recurringQueryKeys.list() });
    },
  });
}

/**
 * Dokument manuell zuordnen
 */
export function useManualMatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      recurringId,
      documentId,
    }: {
      recurringId: string;
      documentId: string;
    }) => manualMatchDocument(recurringId, documentId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: recurringQueryKeys.detail(variables.recurringId),
      });
      queryClient.invalidateQueries({ queryKey: recurringQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: recurringQueryKeys.missing() });
    },
  });
}
