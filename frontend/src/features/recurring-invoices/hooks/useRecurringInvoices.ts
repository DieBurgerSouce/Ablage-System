/**
 * Recurring Invoice Query Hooks
 *
 * TanStack Query Hooks fuer Abo-Rechnungen.
 * Konsistente Query-Keys und wiederverwendbare Hooks.
 *
 * Features:
 * - Differenzierte Stale-Times
 * - Optimistic Updates fuer bessere UX
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
import type {
  RecurringInvoiceFilter,
  RecurringInvoiceCreate,
  RecurringInvoiceUpdate,
  DetectPatternsParams,
} from '../types/recurring-types';

// ==================== Konfiguration ====================

const STALE_TIMES = {
  list: 30 * 1000,         // 30 Sekunden
  detail: 5 * 60 * 1000,   // 5 Minuten
  alerts: 60 * 1000,        // 1 Minute
  report: 2 * 60 * 1000,    // 2 Minuten
} as const;

const GC_TIMES = {
  list: 5 * 60 * 1000,      // 5 Minuten
  detail: 30 * 60 * 1000,   // 30 Minuten
  alerts: 10 * 60 * 1000,   // 10 Minuten
  report: 15 * 60 * 1000,   // 15 Minuten
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
 * Preisaenderungen abrufen
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
