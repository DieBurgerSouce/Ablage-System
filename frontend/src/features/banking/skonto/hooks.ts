/**
 * Skonto React Query Hooks
 *
 * Custom Hooks für Skonto-Daten mit TanStack Query.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/ui/use-toast';
import {
  getSkontoInfo,
  setSkonto,
  applySkonto,
  getUpcomingSkonto,
  getMissedSkonto,
  getSkontoStatistics,
  getMonthlySkontoSummary,
  exportMissedSkonto,
} from './api';
import type {
  SkontoInfo,
  SkontoOpportunity,
  MissedSkontoResponse,
  SkontoStatistics,
  MonthlySkontoSummary,
  ApplySkontoRequest,
  SetSkontoRequest,
  MissedSkontoFilter,
} from './types';
import type { InvoiceTrackingResponse } from '@/features/invoices/types/invoice-types';

// ==================== Query Keys ====================

export const skontoKeys = {
  all: ['skonto'] as const,
  info: (invoiceId: string) => [...skontoKeys.all, 'info', invoiceId] as const,
  upcoming: (daysAhead: number) => [...skontoKeys.all, 'upcoming', daysAhead] as const,
  missed: (filter: MissedSkontoFilter) => [...skontoKeys.all, 'missed', filter] as const,
  statistics: (startDate: string, endDate: string) =>
    [...skontoKeys.all, 'statistics', startDate, endDate] as const,
  monthlySummary: (months: number) => [...skontoKeys.all, 'monthly', months] as const,
};

// ==================== Skonto Info ====================

/**
 * Holt Skonto-Informationen für eine Rechnung
 */
export function useSkontoInfo(invoiceId: string | null | undefined) {
  return useQuery({
    queryKey: skontoKeys.info(invoiceId || ''),
    queryFn: () => getSkontoInfo(invoiceId!),
    enabled: !!invoiceId,
    staleTime: 1000 * 60 * 5, // 5 Minuten
  });
}

/**
 * Setzt Skonto-Konditionen
 */
export function useSetSkonto() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ invoiceId, data }: { invoiceId: string; data: SetSkontoRequest }) =>
      setSkonto(invoiceId, data),
    onSuccess: (updatedInvoice, { invoiceId }) => {
      // Invalidate Skonto Info Query
      queryClient.invalidateQueries({ queryKey: skontoKeys.info(invoiceId) });

      // Invalidate Invoice Queries
      queryClient.invalidateQueries({ queryKey: ['invoices'] });

      toast({
        title: 'Erfolg',
        description: 'Skonto-Konditionen wurden gesetzt',
      });
    },
    onError: (error: Error) => {
      toast({
        variant: 'destructive',
        title: 'Fehler',
        description: error.message || 'Skonto-Konditionen konnten nicht gesetzt werden',
      });
    },
  });
}

/**
 * Wendet Skonto bei einer Zahlung an
 */
export function useApplySkonto() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ invoiceId, data }: { invoiceId: string; data: ApplySkontoRequest }) =>
      applySkonto(invoiceId, data),
    onSuccess: (updatedInvoice, { invoiceId }) => {
      // Invalidate Skonto Queries
      queryClient.invalidateQueries({ queryKey: skontoKeys.info(invoiceId) });
      queryClient.invalidateQueries({ queryKey: skontoKeys.upcoming(7) });

      // Invalidate Invoice Queries
      queryClient.invalidateQueries({ queryKey: ['invoices'] });

      toast({
        title: 'Erfolg',
        description: 'Skonto wurde angewendet',
      });
    },
    onError: (error: Error) => {
      toast({
        variant: 'destructive',
        title: 'Fehler',
        description: error.message || 'Skonto konnte nicht angewendet werden',
      });
    },
  });
}

// ==================== Upcoming Skonto ====================

/**
 * Holt anstehende Skonto-Fristen
 */
export function useUpcomingSkonto(daysAhead: number = 7, limit: number = 20) {
  return useQuery({
    queryKey: skontoKeys.upcoming(daysAhead),
    queryFn: () => getUpcomingSkonto(daysAhead, limit),
    staleTime: 1000 * 60 * 5, // 5 Minuten
    refetchInterval: 1000 * 60 * 15, // Alle 15 Minuten neu laden
  });
}

// ==================== Missed Skonto ====================

/**
 * Holt verpasste Skonto-Möglichkeiten
 */
export function useMissedSkonto(filter: MissedSkontoFilter = {}) {
  return useQuery({
    queryKey: skontoKeys.missed(filter),
    queryFn: () => getMissedSkonto(filter),
    staleTime: 1000 * 60 * 10, // 10 Minuten
  });
}

// ==================== Statistics ====================

/**
 * Holt Skonto-Statistiken für einen Zeitraum
 */
export function useSkontoStatistics(startDate: string, endDate: string) {
  return useQuery({
    queryKey: skontoKeys.statistics(startDate, endDate),
    queryFn: () => getSkontoStatistics(startDate, endDate),
    staleTime: 1000 * 60 * 10, // 10 Minuten
    enabled: !!startDate && !!endDate,
  });
}

/**
 * Holt monatliche Skonto-Zusammenfassung
 */
export function useMonthlySkontoSummary(months: number = 12) {
  return useQuery({
    queryKey: skontoKeys.monthlySummary(months),
    queryFn: () => getMonthlySkontoSummary(months),
    staleTime: 1000 * 60 * 30, // 30 Minuten
  });
}

// ==================== Export ====================

/**
 * Exportiert verpasste Skonto-Daten
 */
export function useExportMissedSkonto() {
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({
      format,
      filter,
    }: {
      format: 'xlsx' | 'csv';
      filter?: Omit<MissedSkontoFilter, 'page' | 'perPage'>;
    }) => exportMissedSkonto(format, filter),
    onSuccess: (blob, { format }) => {
      // Blob als Download bereitstellen
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `verpasste_skonto_${new Date().toISOString().split('T')[0]}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast({
        title: 'Erfolg',
        description: 'Export wurde erstellt',
      });
    },
    onError: (error: Error) => {
      toast({
        variant: 'destructive',
        title: 'Fehler',
        description: error.message || 'Export fehlgeschlagen',
      });
    },
  });
}
