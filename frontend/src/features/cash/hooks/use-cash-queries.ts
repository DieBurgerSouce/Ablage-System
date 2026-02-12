/**
 * Zentrale Query Hooks für Kassenbuch
 * Konsistente Query-Keys und wiederverwendbare Hooks
 *
 * Alle Mutations beinhalten Toast-Messages für User-Feedback.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/ui/use-toast';
import { cashService } from '@/lib/api/services/cash';
import type {
  CashRegisterCreate,
  CashRegisterUpdate,
  CashEntryCreate,
  CashEntryCancelRequest,
  CashCategoryCreate,
  CashCountCreate,
  CashEntryType,
} from '@/types/models/cash';

// ==================== Stale Time Konfiguration ====================

const STALE_TIMES = {
  registers: 5 * 60 * 1000,    // 5 Minuten
  entries: 30 * 1000,          // 30 Sekunden - Einträge können schnell kommen
  categories: 10 * 60 * 1000,  // 10 Minuten - Kategorien ändern sich selten
  counts: 5 * 60 * 1000,       // 5 Minuten
  summary: 2 * 60 * 1000,      // 2 Minuten
} as const;

// ==================== Query Keys ====================

export const cashQueryKeys = {
  all: ['cash'] as const,

  // Registers
  registers: () => [...cashQueryKeys.all, 'registers'] as const,
  registerList: (includeInactive?: boolean) =>
    [...cashQueryKeys.registers(), 'list', includeInactive] as const,
  registerDetail: (id: string) =>
    [...cashQueryKeys.registers(), 'detail', id] as const,

  // Entries
  entries: () => [...cashQueryKeys.all, 'entries'] as const,
  entryList: (params?: {
    register_id?: string;
    start_date?: string;
    end_date?: string;
    entry_type?: CashEntryType;
    skip?: number;
    limit?: number;
  }) => [...cashQueryKeys.entries(), 'list', params] as const,
  entryDetail: (id: string) =>
    [...cashQueryKeys.entries(), 'detail', id] as const,

  // Categories
  categories: () => [...cashQueryKeys.all, 'categories'] as const,
  categoryList: (includeInactive?: boolean) =>
    [...cashQueryKeys.categories(), 'list', includeInactive] as const,

  // Cash Counts
  counts: () => [...cashQueryKeys.all, 'counts'] as const,
  countList: (params?: {
    register_id?: string;
    start_date?: string;
    end_date?: string;
    skip?: number;
    limit?: number;
  }) => [...cashQueryKeys.counts(), 'list', params] as const,

  // Summary
  summary: () => [...cashQueryKeys.all, 'summary'] as const,
  summaryByRegister: (registerId: string, startDate?: string, endDate?: string) =>
    [...cashQueryKeys.summary(), registerId, startDate, endDate] as const,
  dailySummaries: (registerId: string, startDate: string, endDate: string) =>
    [...cashQueryKeys.summary(), 'daily', registerId, startDate, endDate] as const,
};

// ==================== Register Hooks ====================

export function useRegisters(includeInactive = false) {
  return useQuery({
    queryKey: cashQueryKeys.registerList(includeInactive),
    queryFn: () => cashService.listRegisters({ include_inactive: includeInactive }),
    staleTime: STALE_TIMES.registers,
  });
}

export function useRegister(registerId: string) {
  return useQuery({
    queryKey: cashQueryKeys.registerDetail(registerId),
    queryFn: () => cashService.getRegister(registerId),
    staleTime: STALE_TIMES.registers,
    enabled: !!registerId,
  });
}

export function useCreateRegister() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: CashRegisterCreate) => cashService.createRegister(data),
    onSuccess: (register) => {
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.registers() });
      toast({
        title: CASH_TOAST_MESSAGES.register.success,
        description: `"${register.name}" wurde erstellt`,
        variant: 'success',
      });
    },
    onError: (error: Error) => {
      toast({
        title: CASH_TOAST_MESSAGES.register.error,
        description: error.message,
        variant: 'destructive',
      });
    },
  });
}

export function useUpdateRegister() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CashRegisterUpdate }) =>
      cashService.updateRegister(id, data),
    onSuccess: (register, { id }) => {
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.registers() });
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.registerDetail(id) });
      toast({
        title: 'Kasse aktualisiert',
        description: `"${register.name}" wurde gespeichert`,
        variant: 'success',
      });
    },
    onError: (error: Error) => {
      toast({
        title: 'Fehler beim Aktualisieren',
        description: error.message,
        variant: 'destructive',
      });
    },
  });
}

// ==================== Entry Hooks ====================

export function useEntries(params?: {
  register_id?: string;
  start_date?: string;
  end_date?: string;
  entry_type?: CashEntryType;
  skip?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: cashQueryKeys.entryList(params),
    queryFn: () => cashService.listEntries(params),
    staleTime: STALE_TIMES.entries,
  });
}

export function useEntry(entryId: string) {
  return useQuery({
    queryKey: cashQueryKeys.entryDetail(entryId),
    queryFn: () => cashService.getEntry(entryId),
    staleTime: STALE_TIMES.entries,
    enabled: !!entryId,
  });
}

export function useCreateEntry(options?: {
  onSuccess?: (entry: unknown) => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: CashEntryCreate) => cashService.createEntry(data),
    onSuccess: (entry) => {
      // Invalidate entries list
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.entries() });
      // Invalidate register (balance changed)
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.registerDetail(entry.register_id) });
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.registers() });
      // Invalidate summary
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.summary() });

      // Toast-Feedback
      toast({
        title: CASH_TOAST_MESSAGES.createEntry.success,
        description: `Beleg-Nr. ${entry.entry_number}: ${entry.description?.substring(0, 40) || 'Buchung'}`,
        variant: 'success',
      });

      // Custom callback
      options?.onSuccess?.(entry);
    },
    onError: (error: Error) => {
      toast({
        title: CASH_TOAST_MESSAGES.createEntry.error,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

export function useCancelEntry(options?: {
  onSuccess?: (entry: unknown) => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ entryId, data }: { entryId: string; data: CashEntryCancelRequest }) =>
      cashService.cancelEntry(entryId, data),
    onSuccess: (cancellationEntry) => {
      // Invalidate entries
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.entries() });
      // Invalidate register (balance changed)
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.registerDetail(cancellationEntry.register_id) });
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.registers() });
      // Invalidate summary
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.summary() });

      // Toast-Feedback
      toast({
        title: CASH_TOAST_MESSAGES.cancelEntry.success,
        description: 'Stornobuchung wurde erstellt',
        variant: 'success',
      });

      // Custom callback
      options?.onSuccess?.(cancellationEntry);
    },
    onError: (error: Error) => {
      toast({
        title: CASH_TOAST_MESSAGES.cancelEntry.error,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

// ==================== Category Hooks ====================

export function useCategories(includeInactive = false) {
  return useQuery({
    queryKey: cashQueryKeys.categoryList(includeInactive),
    queryFn: () => cashService.listCategories({ include_inactive: includeInactive }),
    staleTime: STALE_TIMES.categories,
  });
}

export function useCreateCategory() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: CashCategoryCreate) => cashService.createCategory(data),
    onSuccess: (category) => {
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.categories() });
      toast({
        title: CASH_TOAST_MESSAGES.category.success,
        description: `"${category.name}" wurde angelegt`,
        variant: 'success',
      });
    },
    onError: (error: Error) => {
      toast({
        title: CASH_TOAST_MESSAGES.category.error,
        description: error.message,
        variant: 'destructive',
      });
    },
  });
}

// ==================== Cash Count Hooks ====================

export function useCashCounts(params?: {
  register_id?: string;
  start_date?: string;
  end_date?: string;
  skip?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: cashQueryKeys.countList(params),
    queryFn: () => cashService.listCashCounts(params),
    staleTime: STALE_TIMES.counts,
  });
}

export function usePerformCashCount(options?: {
  onSuccess?: (cashCount: unknown) => void;
  onError?: (error: Error) => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (data: CashCountCreate) => cashService.performCashCount(data),
    onSuccess: (cashCount) => {
      // Invalidate counts
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.counts() });
      // Invalidate register (may have adjustment entry)
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.registerDetail(cashCount.register_id) });
      queryClient.invalidateQueries({ queryKey: cashQueryKeys.registers() });
      // Invalidate entries (adjustment entry created)
      if (cashCount.adjustment_entry_id) {
        queryClient.invalidateQueries({ queryKey: cashQueryKeys.entries() });
      }

      // Toast-Feedback - unterscheide zwischen mit/ohne Differenz
      const hasAdjustment = !!cashCount.adjustment_entry_id;
      toast({
        title: hasAdjustment
          ? CASH_TOAST_MESSAGES.cashCount.successWithDifference
          : CASH_TOAST_MESSAGES.cashCount.success,
        description: hasAdjustment
          ? `Differenz: ${cashCount.difference?.toFixed(2) || '0.00'} EUR`
          : `Gezaehlt: ${cashCount.counted_amount?.toFixed(2) || '0.00'} EUR`,
        variant: 'success',
      });

      // Custom callback
      options?.onSuccess?.(cashCount);
    },
    onError: (error: Error) => {
      toast({
        title: CASH_TOAST_MESSAGES.cashCount.error,
        description: error.message,
        variant: 'destructive',
      });
      options?.onError?.(error);
    },
  });
}

// ==================== Summary Hooks ====================

export function useCashSummary(
  registerId: string,
  startDate?: string,
  endDate?: string
) {
  return useQuery({
    queryKey: cashQueryKeys.summaryByRegister(registerId, startDate, endDate),
    queryFn: () => cashService.getSummary({
      register_id: registerId,
      start_date: startDate,
      end_date: endDate,
    }),
    staleTime: STALE_TIMES.summary,
    enabled: !!registerId,
  });
}

export function useDailySummaries(
  registerId: string,
  startDate: string,
  endDate: string
) {
  return useQuery({
    queryKey: cashQueryKeys.dailySummaries(registerId, startDate, endDate),
    queryFn: () => cashService.getDailySummaries({
      register_id: registerId,
      start_date: startDate,
      end_date: endDate,
    }),
    staleTime: STALE_TIMES.summary,
    enabled: !!registerId && !!startDate && !!endDate,
  });
}

// ==================== Toast Messages ====================

/**
 * Standard-Toast-Nachrichten für Kassen-Operationen.
 * Verwendung in Komponenten für konsistentes deutsches Feedback.
 */
export const CASH_TOAST_MESSAGES = {
  createEntry: {
    success: 'Buchung erfolgreich erstellt',
    error: 'Fehler beim Erstellen der Buchung',
  },
  cancelEntry: {
    success: 'Buchung erfolgreich storniert',
    error: 'Fehler beim Stornieren der Buchung',
  },
  cashCount: {
    success: 'Kassensturz erfolgreich durchgeführt',
    successWithDifference: 'Kassensturz erfolgreich - Ausgleichsbuchung erstellt',
    error: 'Fehler beim Kassensturz',
  },
  register: {
    success: 'Kasse erfolgreich erstellt',
    error: 'Fehler beim Erstellen der Kasse',
  },
  category: {
    success: 'Kategorie erfolgreich erstellt',
    error: 'Fehler beim Erstellen der Kategorie',
  },
} as const;
