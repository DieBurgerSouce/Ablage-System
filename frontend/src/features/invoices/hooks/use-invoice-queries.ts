/**
 * Invoice Query Hooks
 *
 * TanStack Query Hooks für Rechnungsverfolgung.
 * Konsistente Query-Keys und wiederverwendbare Hooks.
 *
 * Features:
 * - Differenzierte Stale-Times
 * - Optimistic Updates für bessere UX
 * - Error Retry mit Backoff
 */

import { useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { invoiceService, InvoiceApiError } from '../api/invoice-api';
import type {
  InvoiceFilter,
  InvoiceTrackingCreate,
  InvoiceTrackingUpdate,
  InvoiceTrackingResponse,
  SkontoUpdate,
  PaymentCreate,
} from '../types/invoice-types';

// ==================== Konfiguration ====================

const STALE_TIMES = {
  invoices: 30 * 1000,       // 30 Sekunden - Rechnungen können sich schnell ändern
  statistics: 60 * 1000,      // 1 Minute - Statistiken ändern sich seltener
  detail: 5 * 60 * 1000,      // 5 Minuten - Einzelne Rechnung ändert sich selten
} as const;

const GC_TIMES = {
  invoices: 5 * 60 * 1000,    // 5 Minuten - Listen aus Cache entfernen
  statistics: 10 * 60 * 1000, // 10 Minuten - Statistiken länger halten
  detail: 30 * 60 * 1000,     // 30 Minuten - Details lange halten
} as const;

const RETRY_CONFIG = {
  retry: (failureCount: number, error: unknown) => {
    // Keine Retries bei 4xx Fehlern (Client-Fehler)
    if (error instanceof InvoiceApiError && error.statusCode) {
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

export const invoiceQueryKeys = {
  all: ['invoices'] as const,

  // Rechnungsliste
  list: () => [...invoiceQueryKeys.all, 'list'] as const,
  listFiltered: (filter: Partial<InvoiceFilter>) =>
    [...invoiceQueryKeys.list(), filter] as const,

  // Statistiken
  statistics: () => [...invoiceQueryKeys.all, 'statistics'] as const,

  // Einzelne Rechnung
  detail: (id: string) => [...invoiceQueryKeys.all, 'detail', id] as const,

  // Skonto
  skonto: (id: string) => [...invoiceQueryKeys.all, 'skonto', id] as const,
  upcomingSkonto: (daysAhead: number) =>
    [...invoiceQueryKeys.all, 'upcoming-skonto', daysAhead] as const,

  // Teilzahlungen
  payments: (id: string) => [...invoiceQueryKeys.all, 'payments', id] as const,
};

// ==================== Query Hooks ====================

/**
 * Rechnungen mit Filter und Pagination abrufen
 */
export function useInvoices(
  filter: Partial<InvoiceFilter> = {},
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: invoiceQueryKeys.listFiltered(filter),
    queryFn: () => invoiceService.listInvoices(filter),
    staleTime: STALE_TIMES.invoices,
    gcTime: GC_TIMES.invoices,
    enabled: options?.enabled !== false,
    placeholderData: (previousData) => previousData,
    ...RETRY_CONFIG,
  });
}

/**
 * Rechnungsstatistiken abrufen
 */
export function useInvoiceStatistics(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: invoiceQueryKeys.statistics(),
    queryFn: () => invoiceService.getStatistics(),
    staleTime: STALE_TIMES.statistics,
    gcTime: GC_TIMES.statistics,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

/**
 * Einzelne Rechnung abrufen
 */
export function useInvoice(invoiceId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: invoiceQueryKeys.detail(invoiceId),
    queryFn: () => invoiceService.getInvoice(invoiceId),
    staleTime: STALE_TIMES.detail,
    gcTime: GC_TIMES.detail,
    enabled: options?.enabled !== false && !!invoiceId,
    ...RETRY_CONFIG,
  });
}

// ==================== Mutation Hooks ====================

/**
 * Rechnungsverfolgung erstellen
 */
export function useCreateInvoice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: InvoiceTrackingCreate) =>
      invoiceService.createInvoice(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.statistics() });
    },
  });
}

/**
 * Rechnungsverfolgung aktualisieren
 */
export function useUpdateInvoice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      invoiceId,
      data,
    }: {
      invoiceId: string;
      data: InvoiceTrackingUpdate;
    }) => invoiceService.updateInvoice(invoiceId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.detail(variables.invoiceId),
      });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.statistics() });
    },
  });
}

/**
 * Als bezahlt markieren
 */
export function useMarkInvoicePaid() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      invoiceId,
      paidAmount,
      paidAt,
    }: {
      invoiceId: string;
      paidAmount?: number;
      paidAt?: string;
    }) => invoiceService.markPaid(invoiceId, { paidAmount, paidAt }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.detail(variables.invoiceId),
      });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.statistics() });
    },
  });
}

/**
 * Mahnstufe erhöhen
 */
export function useIncreaseDunning() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (invoiceId: string) =>
      invoiceService.increaseDunning(invoiceId),
    onSuccess: (updatedInvoice) => {
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.detail(updatedInvoice.id),
      });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.statistics() });
    },
  });
}

/**
 * Rechnungsverfolgung löschen
 */
export function useDeleteInvoice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (invoiceId: string) => invoiceService.deleteInvoice(invoiceId),
    onSuccess: (_, invoiceId) => {
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.detail(invoiceId),
      });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.statistics() });
    },
  });
}

// ==================== Skonto Hooks ====================

/**
 * Skonto-Informationen einer Rechnung abrufen
 */
export function useSkonto(invoiceId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: invoiceQueryKeys.skonto(invoiceId),
    queryFn: () => invoiceService.getSkonto(invoiceId),
    staleTime: STALE_TIMES.detail,
    gcTime: GC_TIMES.detail,
    enabled: options?.enabled !== false && !!invoiceId,
    ...RETRY_CONFIG,
  });
}

/**
 * Bevorstehende Skonto-Fristen abrufen
 */
export function useUpcomingSkontoDeadlines(
  daysAhead: number = 7,
  options?: { enabled?: boolean }
) {
  return useQuery({
    queryKey: invoiceQueryKeys.upcomingSkonto(daysAhead),
    queryFn: () => invoiceService.getUpcomingSkontoDeadlines(daysAhead),
    staleTime: STALE_TIMES.statistics, // Wie Statistiken - ändert sich nicht so oft
    gcTime: GC_TIMES.statistics,
    enabled: options?.enabled !== false,
    ...RETRY_CONFIG,
  });
}

/**
 * Skonto-Bedingungen aktualisieren
 */
export function useUpdateSkonto() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      invoiceId,
      data,
    }: {
      invoiceId: string;
      data: SkontoUpdate;
    }) => invoiceService.updateSkonto(invoiceId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.skonto(variables.invoiceId),
      });
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.detail(variables.invoiceId),
      });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.list() });
    },
  });
}

/**
 * Skonto anwenden (mit Skonto bezahlen)
 */
export function useApplySkonto() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (invoiceId: string) => invoiceService.applySkonto(invoiceId),
    onSuccess: (updatedInvoice) => {
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.skonto(updatedInvoice.id),
      });
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.detail(updatedInvoice.id),
      });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.statistics() });
      // Auch die upcoming-Skonto Liste invalidieren
      queryClient.invalidateQueries({
        predicate: (query) =>
          Array.isArray(query.queryKey) &&
          query.queryKey[0] === 'invoices' &&
          query.queryKey[1] === 'upcoming-skonto',
      });
    },
  });
}

// ==================== Teilzahlung Hooks ====================

/**
 * Zahlungen einer Rechnung abrufen
 */
export function usePayments(invoiceId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: invoiceQueryKeys.payments(invoiceId),
    queryFn: () => invoiceService.listPayments(invoiceId),
    staleTime: STALE_TIMES.invoices, // Zahlungen können sich schnell ändern
    gcTime: GC_TIMES.invoices,
    enabled: options?.enabled !== false && !!invoiceId,
    ...RETRY_CONFIG,
  });
}

/**
 * Teilzahlung erfassen
 */
export function useAddPayment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      invoiceId,
      data,
    }: {
      invoiceId: string;
      data: PaymentCreate;
    }) => invoiceService.addPayment(invoiceId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.payments(variables.invoiceId),
      });
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.detail(variables.invoiceId),
      });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.statistics() });
    },
  });
}

/**
 * Teilzahlung löschen
 */
export function useDeletePayment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      invoiceId,
      paymentId,
    }: {
      invoiceId: string;
      paymentId: string;
    }) => invoiceService.deletePayment(invoiceId, paymentId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.payments(variables.invoiceId),
      });
      queryClient.invalidateQueries({
        queryKey: invoiceQueryKeys.detail(variables.invoiceId),
      });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.list() });
      queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.statistics() });
    },
  });
}

// ==================== Combined Hooks ====================

/**
 * Kombinierter Hook für Rechnungs-Seite
 * Lädt sowohl Rechnungen als auch Statistiken
 */
export function useInvoicePage(
  filter: Partial<InvoiceFilter> = {},
  options?: { enabled?: boolean }
) {
  const isEnabled = options?.enabled !== false;

  const invoicesQuery = useInvoices(filter, { enabled: isEnabled });
  const statisticsQuery = useInvoiceStatistics({ enabled: isEnabled });

  return {
    // Daten
    invoices: invoicesQuery.data ?? [],
    statistics: statisticsQuery.data,

    // Ladezustand
    isLoading: invoicesQuery.isLoading || statisticsQuery.isLoading,
    isLoadingInvoices: invoicesQuery.isLoading,
    isLoadingStatistics: statisticsQuery.isLoading,
    isFetching: invoicesQuery.isFetching || statisticsQuery.isFetching,

    // Fehlerzustand
    isError: invoicesQuery.isError || statisticsQuery.isError,
    error: invoicesQuery.error || statisticsQuery.error,
    invoicesError: invoicesQuery.error,
    statisticsError: statisticsQuery.error,

    // Aktionen
    refetch: () => {
      invoicesQuery.refetch();
      statisticsQuery.refetch();
    },
    refetchInvoices: invoicesQuery.refetch,
    refetchStatistics: statisticsQuery.refetch,
  };
}

/**
 * Kombinierter Hook für alle Rechnungs-Mutationen
 */
export function useInvoiceMutations() {
  const createInvoice = useCreateInvoice();
  const updateInvoice = useUpdateInvoice();
  const markPaid = useMarkInvoicePaid();
  const increaseDunning = useIncreaseDunning();
  const deleteInvoice = useDeleteInvoice();

  const isAnyMutating =
    createInvoice.isPending ||
    updateInvoice.isPending ||
    markPaid.isPending ||
    increaseDunning.isPending ||
    deleteInvoice.isPending;

  return {
    // Mutations
    createInvoice,
    updateInvoice,
    markPaid,
    increaseDunning,
    deleteInvoice,

    // Status
    isAnyMutating,
  };
}

// ==================== Prefetch Helpers ====================

/**
 * Prefetch für Rechnungsliste (z.B. beim Hover über Navigation)
 */
export function usePrefetchInvoices() {
  const queryClient = useQueryClient();

  const prefetch = useCallback(
    (filter: Partial<InvoiceFilter> = {}) => {
      queryClient.prefetchQuery({
        queryKey: invoiceQueryKeys.listFiltered(filter),
        queryFn: () => invoiceService.listInvoices(filter),
        staleTime: STALE_TIMES.invoices,
      });
    },
    [queryClient]
  );

  return prefetch;
}

/**
 * Prefetch für Rechnungs-Seite (Rechnungen + Statistiken)
 */
export function usePrefetchInvoicePage() {
  const queryClient = useQueryClient();

  const prefetch = useCallback(
    (filter: Partial<InvoiceFilter> = {}) => {
      // Prefetch Rechnungen
      queryClient.prefetchQuery({
        queryKey: invoiceQueryKeys.listFiltered(filter),
        queryFn: () => invoiceService.listInvoices(filter),
        staleTime: STALE_TIMES.invoices,
      });

      // Prefetch Statistiken
      queryClient.prefetchQuery({
        queryKey: invoiceQueryKeys.statistics(),
        queryFn: () => invoiceService.getStatistics(),
        staleTime: STALE_TIMES.statistics,
      });
    },
    [queryClient]
  );

  return prefetch;
}

// ==================== Utility Helpers ====================

/**
 * Invalidiert alle Rechnungs-relevanten Queries
 */
export function useInvalidateInvoiceQueries() {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: invoiceQueryKeys.all });
  }, [queryClient]);
}
