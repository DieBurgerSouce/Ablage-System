/**
 * Zentrale Query Hooks fuer Banking Dashboard
 * Konsistente Query-Keys und wiederverwendbare Hooks
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { bankingService } from '@/lib/api/services/banking';

// ==================== Stale Time Konfiguration ====================
// Definiert wie lange Daten als "frisch" gelten bevor sie refetched werden

const STALE_TIMES = {
    stats: 5 * 60 * 1000,      // 5 Minuten - Stats aendern sich selten
    aging: 2 * 60 * 1000,      // 2 Minuten - Aging kann sich durch Zahlungen aendern
    cashflow: 5 * 60 * 1000,   // 5 Minuten - Prognosen aendern sich selten
    dunning: 1 * 60 * 1000,    // 1 Minute - Mahnstatus kann sich schnell aendern
    transactions: 30 * 1000,   // 30 Sekunden - Transaktionen koennen schnell kommen
} as const;

// ==================== Query Keys ====================

export const bankingQueryKeys = {
    all: ['banking'] as const,

    // Cash-Flow
    cashflow: () => [...bankingQueryKeys.all, 'cashflow'] as const,
    cashflowForecast: (days?: number, scenario?: string) =>
        [...bankingQueryKeys.cashflow(), 'forecast', days, scenario] as const,
    cashflowSummary: () => [...bankingQueryKeys.cashflow(), 'summary'] as const,
    cashflowDaily: (days: number) => [...bankingQueryKeys.cashflow(), 'daily', days] as const,
    cashflowScenarios: (days?: number) => [...bankingQueryKeys.cashflow(), 'scenarios', days] as const,

    // Dunning
    dunning: () => [...bankingQueryKeys.all, 'dunning'] as const,
    dunningStats: () => [...bankingQueryKeys.dunning(), 'stats'] as const,
    overdueInvoices: (minDays?: number, maxDays?: number) =>
        [...bankingQueryKeys.dunning(), 'overdue', minDays, maxDays] as const,

    // Aging
    aging: () => [...bankingQueryKeys.all, 'aging'] as const,
    agingSummary: () => [...bankingQueryKeys.aging(), 'summary'] as const,
    agingReceivables: (counterparty?: string) =>
        [...bankingQueryKeys.aging(), 'receivables', counterparty] as const,
    agingPayables: (counterparty?: string) =>
        [...bankingQueryKeys.aging(), 'payables', counterparty] as const,
    topDebtors: (limit: number) => [...bankingQueryKeys.aging(), 'top-debtors', limit] as const,
    topCreditors: (limit: number) => [...bankingQueryKeys.aging(), 'top-creditors', limit] as const,
    dso: (periodDays: number) => [...bankingQueryKeys.aging(), 'dso', periodDays] as const,

    // Transactions
    transactions: () => [...bankingQueryKeys.all, 'transactions'] as const,
    transactionStats: (params?: { bank_account_id?: string; date_from?: string; date_to?: string }) =>
        [...bankingQueryKeys.transactions(), 'stats', params?.bank_account_id, params?.date_from, params?.date_to] as const,

    // Accounts
    accounts: () => [...bankingQueryKeys.all, 'accounts'] as const,
    accountsWithStats: () => [...bankingQueryKeys.accounts(), 'with-stats'] as const,
};

// ==================== Cash-Flow Hooks ====================

/**
 * Cash-Flow-Prognose abrufen
 */
export function useCashFlowForecast(params?: {
    days_ahead?: number;
    scenario?: 'optimistic' | 'realistic' | 'pessimistic';
    bank_account_id?: string;
}) {
    return useQuery({
        queryKey: bankingQueryKeys.cashflowForecast(params?.days_ahead, params?.scenario),
        queryFn: () => bankingService.getCashFlowForecast(params),
        staleTime: STALE_TIMES.cashflow,
    });
}

/**
 * Cash-Flow-Zusammenfassung abrufen
 */
export function useCashFlowSummary(bankAccountId?: string) {
    return useQuery({
        queryKey: bankingQueryKeys.cashflowSummary(),
        queryFn: () => bankingService.getCashFlowSummary({ bank_account_id: bankAccountId }),
        staleTime: STALE_TIMES.cashflow,
    });
}

/**
 * Taegliche Cash-Flow-Daten fuer Charts
 */
export function useCashFlowDaily(days = 30, bankAccountId?: string) {
    return useQuery({
        queryKey: bankingQueryKeys.cashflowDaily(days),
        queryFn: () => bankingService.getCashFlowDaily({ days, bank_account_id: bankAccountId }),
        staleTime: STALE_TIMES.cashflow,
    });
}

/**
 * Szenario-Vergleich (Optimistisch/Realistisch/Pessimistisch)
 */
export function useCashFlowScenarios(daysAhead = 90, bankAccountId?: string) {
    return useQuery({
        queryKey: bankingQueryKeys.cashflowScenarios(daysAhead),
        queryFn: () => bankingService.getCashFlowScenarios({ days_ahead: daysAhead, bank_account_id: bankAccountId }),
        staleTime: STALE_TIMES.cashflow,
    });
}

// ==================== Dunning Hooks ====================

/**
 * Mahnstatistiken abrufen
 */
export function useDunningStats() {
    return useQuery({
        queryKey: bankingQueryKeys.dunningStats(),
        queryFn: () => bankingService.getDunningStats(),
        staleTime: STALE_TIMES.dunning,
    });
}

/**
 * Ueberfaellige Rechnungen abrufen
 */
export function useOverdueInvoices(params?: { min_days?: number; max_days?: number }) {
    return useQuery({
        queryKey: bankingQueryKeys.overdueInvoices(params?.min_days, params?.max_days),
        queryFn: () => bankingService.getOverdueInvoices(params),
        staleTime: STALE_TIMES.dunning,
    });
}

/**
 * Mahnvorgang erstellen
 */
export function useCreateDunning() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (params: { document_id: string; level?: string; notes?: string }) =>
            bankingService.createDunning(params),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

/**
 * Mahnvorgang eskalieren
 */
export function useEscalateDunning() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ dunningId, notes }: { dunningId: string; notes?: string }) =>
            bankingService.escalateDunning(dunningId, notes),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

/**
 * Mahnvorgang schliessen
 */
export function useCloseDunning() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ dunningId, status, notes }: { dunningId: string; status: string; notes?: string }) =>
            bankingService.closeDunning(dunningId, status, notes),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

// ==================== Aging Hooks ====================

/**
 * Altersanalyse-Zusammenfassung
 */
export function useAgingSummary() {
    return useQuery({
        queryKey: bankingQueryKeys.agingSummary(),
        queryFn: () => bankingService.getAgingSummary(),
        staleTime: STALE_TIMES.aging,
    });
}

/**
 * Forderungs-Altersanalyse
 */
export function useReceivablesAging(counterparty?: string, enabled = true) {
    return useQuery({
        queryKey: bankingQueryKeys.agingReceivables(counterparty),
        queryFn: () => bankingService.getReceivablesAging({ counterparty }),
        staleTime: STALE_TIMES.aging,
        enabled,
    });
}

/**
 * Verbindlichkeiten-Altersanalyse
 */
export function usePayablesAging(counterparty?: string, enabled = true) {
    return useQuery({
        queryKey: bankingQueryKeys.agingPayables(counterparty),
        queryFn: () => bankingService.getPayablesAging({ counterparty }),
        staleTime: STALE_TIMES.aging,
        enabled,
    });
}

/**
 * Top-Schuldner
 */
export function useTopDebtors(limit = 10, enabled = true) {
    return useQuery({
        queryKey: bankingQueryKeys.topDebtors(limit),
        queryFn: () => bankingService.getTopDebtors(limit),
        staleTime: STALE_TIMES.aging,
        enabled,
    });
}

/**
 * Top-Glaeubiger
 */
export function useTopCreditors(limit = 10, enabled = true) {
    return useQuery({
        queryKey: bankingQueryKeys.topCreditors(limit),
        queryFn: () => bankingService.getTopCreditors(limit),
        staleTime: STALE_TIMES.aging,
        enabled,
    });
}

/**
 * Days Sales Outstanding
 */
export function useDSO(periodDays = 90) {
    return useQuery({
        queryKey: bankingQueryKeys.dso(periodDays),
        queryFn: () => bankingService.getDSO(periodDays),
        staleTime: STALE_TIMES.stats,
    });
}

// ==================== Transaction Hooks ====================

/**
 * Transaktions-Statistiken
 */
export function useTransactionStats(params?: { bank_account_id?: string; date_from?: string; date_to?: string }) {
    return useQuery({
        queryKey: bankingQueryKeys.transactionStats(params),
        queryFn: () => bankingService.getTransactionStats(params),
        staleTime: STALE_TIMES.transactions,
    });
}

// ==================== Account Hooks ====================

/**
 * Bankkonten mit Statistiken
 */
export function useAccountsWithStats() {
    return useQuery({
        queryKey: bankingQueryKeys.accountsWithStats(),
        queryFn: () => bankingService.getAccountsWithStats(),
        staleTime: STALE_TIMES.stats,
    });
}

// ==================== Reconciliation Hooks ====================

/**
 * Batch-Abgleich durchfuehren
 */
export function useBatchReconcile() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (params?: { bank_account_id?: string; limit?: number }) =>
            bankingService.batchReconcile(params),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.aging() });
        },
    });
}
