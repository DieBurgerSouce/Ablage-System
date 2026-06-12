/**
 * Zentrale Query Hooks für Banking Dashboard
 * Konsistente Query-Keys und wiederverwendbare Hooks
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { bankingService } from '@/lib/api/services/banking';
import { QUERY_VOLATILE, QUERY_STANDARD, QUERY_SEMI_STATIC } from '@/lib/api/query-config';

// ==================== Stale Time Konfiguration ====================
// Definiert wie lange Daten als "frisch" gelten bevor sie refetched werden

const STALE_TIMES = {
    stats: QUERY_SEMI_STATIC.staleTime,    // 5min - Stats ändern sich selten
    aging: QUERY_STANDARD.staleTime,       // 60s - Aging kann sich durch Zahlungen ändern
    cashflow: QUERY_SEMI_STATIC.staleTime, // 5min - Prognosen ändern sich selten
    dunning: QUERY_STANDARD.staleTime,     // 60s - Mahnstatus kann sich schnell ändern
    transactions: QUERY_VOLATILE.staleTime, // 30s - Transaktionen können schnell kommen
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

    // Transactions (Extended)
    transactions: () => [...bankingQueryKeys.all, 'transactions'] as const,
    transactionStats: (params?: { bank_account_id?: string; date_from?: string; date_to?: string }) =>
        [...bankingQueryKeys.transactions(), 'stats', params?.bank_account_id, params?.date_from, params?.date_to] as const,
    transactionList: (filters: unknown) =>
        [...bankingQueryKeys.transactions(), 'list', filters] as const,
    transactionDetail: (id: string) =>
        [...bankingQueryKeys.transactions(), 'detail', id] as const,
    unmatchedTransactions: (bankAccountId?: string) =>
        [...bankingQueryKeys.transactions(), 'unmatched', bankAccountId] as const,
    monthlyTransactionSummary: (bankAccountId?: string) =>
        [...bankingQueryKeys.transactions(), 'monthly', bankAccountId] as const,

    // Accounts (Extended)
    accounts: () => [...bankingQueryKeys.all, 'accounts'] as const,
    accountsWithStats: () => [...bankingQueryKeys.accounts(), 'with-stats'] as const,
    accountList: (includeInactive?: boolean) =>
        [...bankingQueryKeys.accounts(), 'list', includeInactive] as const,
    accountDetail: (id: string) =>
        [...bankingQueryKeys.accounts(), 'detail', id] as const,

    // Import
    import: () => [...bankingQueryKeys.all, 'import'] as const,
    supportedFormats: () => [...bankingQueryKeys.import(), 'formats'] as const,
    importHistory: (bankAccountId?: string) =>
        [...bankingQueryKeys.import(), 'history', bankAccountId] as const,

    // Reconciliation
    reconciliation: () => [...bankingQueryKeys.all, 'reconciliation'] as const,
    matchSuggestions: (transactionId: string) =>
        [...bankingQueryKeys.reconciliation(), 'suggestions', transactionId] as const,

    // Payments
    payments: () => [...bankingQueryKeys.all, 'payments'] as const,
    paymentList: (params?: Record<string, unknown>) =>
        [...bankingQueryKeys.payments(), 'list', params] as const,
    paymentDetail: (id: string) =>
        [...bankingQueryKeys.payments(), 'detail', id] as const,
    pendingPayments: () =>
        [...bankingQueryKeys.payments(), 'pending'] as const,
    tanMethods: () =>
        [...bankingQueryKeys.payments(), 'tan-methods'] as const,

    // Skonto
    skonto: () => [...bankingQueryKeys.all, 'skonto'] as const,
    skontoOpportunities: (daysAhead?: number) =>
        [...bankingQueryKeys.skonto(), 'opportunities', daysAhead] as const,

    // Liquidity Forecast
    liquidity: () => [...bankingQueryKeys.all, 'liquidity'] as const,
    liquidityForecast: (bankAccountId?: string) =>
        [...bankingQueryKeys.liquidity(), 'forecast', bankAccountId] as const,
    liquidityBottlenecks: (params?: { bankAccountId?: string; daysAhead?: number }) =>
        [...bankingQueryKeys.liquidity(), 'bottlenecks', params?.bankAccountId, params?.daysAhead] as const,
    liquidityWaterfall: (params?: { bankAccountId?: string; days?: number; granularity?: string }) =>
        [...bankingQueryKeys.liquidity(), 'waterfall', params?.bankAccountId, params?.days, params?.granularity] as const,
    liquidityAnomalies: (params?: { bankAccountId?: string; daysBack?: number }) =>
        [...bankingQueryKeys.liquidity(), 'anomalies', params?.bankAccountId, params?.daysBack] as const,
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
 * Tägliche Cash-Flow-Daten für Charts
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
 * Überfällige Rechnungen abrufen
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
 * Akzeptiert entweder einen String (dunningId) oder ein Objekt { dunningId, notes }
 */
export function useEscalateDunning() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (params: string | { dunningId: string; notes?: string }) => {
            const dunningId = typeof params === 'string' ? params : params.dunningId;
            const notes = typeof params === 'string' ? undefined : params.notes;
            return bankingService.escalateDunning(dunningId, notes);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

/**
 * Mahnvorgang schließen
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
 * Top-Gläubiger
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
 * Batch-Abgleich durchführen
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

/**
 * Match-Vorschläge für eine Transaktion abrufen
 */
export function useMatchSuggestions(transactionId: string, limit = 5, enabled = true) {
    return useQuery({
        queryKey: bankingQueryKeys.matchSuggestions(transactionId),
        queryFn: () => bankingService.getMatchSuggestions(transactionId, limit),
        staleTime: STALE_TIMES.transactions,
        enabled: enabled && !!transactionId,
    });
}

/**
 * Manueller Abgleich
 */
export function useManualMatch() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ transactionId, documentId, notes }: { transactionId: string; documentId: string; notes?: string }) =>
            bankingService.manualMatch(transactionId, documentId, notes),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.reconciliation() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.aging() });
        },
    });
}

/**
 * Abgleich aufheben
 */
export function useUnmatchTransaction() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (transactionId: string) => bankingService.unmatchTransaction(transactionId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.reconciliation() });
        },
    });
}

/**
 * Transaktion aufteilen (Split)
 */
export function useSplitTransaction() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ transactionId, splits }: { transactionId: string; splits: { document_id: string; amount: number }[] }) =>
            bankingService.splitTransaction(transactionId, splits),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.reconciliation() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.aging() });
        },
    });
}

/**
 * Auto-Abgleich für einzelne Transaktion
 */
export function useAutoReconcileSingle() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (transactionId: string) => bankingService.autoReconcileSingle(transactionId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.reconciliation() });
        },
    });
}

// ==================== Account Hooks (Extended) ====================

/**
 * Alle Bankkonten abrufen
 */
export function useAccounts(includeInactive = false) {
    return useQuery({
        queryKey: bankingQueryKeys.accountList(includeInactive),
        queryFn: () => bankingService.getAccounts(includeInactive),
        staleTime: STALE_TIMES.stats,
    });
}

/**
 * Einzelnes Bankkonto abrufen
 */
export function useAccount(id: string, enabled = true) {
    return useQuery({
        queryKey: bankingQueryKeys.accountDetail(id),
        queryFn: () => bankingService.getAccount(id),
        staleTime: STALE_TIMES.stats,
        enabled: enabled && !!id,
    });
}

/**
 * Bankkonto erstellen
 */
export function useCreateAccount() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: bankingService.createAccount,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.accounts() });
        },
    });
}

/**
 * Bankkonto aktualisieren
 */
export function useUpdateAccount() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, data }: { id: string; data: Parameters<typeof bankingService.updateAccount>[1] }) =>
            bankingService.updateAccount(id, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.accounts() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.accountDetail(variables.id) });
        },
    });
}

/**
 * Bankkonto löschen
 */
export function useDeleteAccount() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: bankingService.deleteAccount,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.accounts() });
        },
    });
}

// ==================== Transaction Hooks (Extended) ====================

/**
 * Transaktionsliste mit Filter und Pagination
 */
export function useTransactions(
    filters: Parameters<typeof bankingService.getTransactions>[0],
    enabled = true
) {
    return useQuery({
        queryKey: bankingQueryKeys.transactionList(filters),
        queryFn: () => bankingService.getTransactions(filters),
        staleTime: STALE_TIMES.transactions,
        enabled,
    });
}

/**
 * Einzelne Transaktion abrufen
 */
export function useTransaction(id: string, enabled = true) {
    return useQuery({
        queryKey: bankingQueryKeys.transactionDetail(id),
        queryFn: () => bankingService.getTransaction(id),
        staleTime: STALE_TIMES.transactions,
        enabled: enabled && !!id,
    });
}

/**
 * Unabgeglichene Transaktionen
 */
export function useUnmatchedTransactions(bankAccountId?: string, limit = 50) {
    return useQuery({
        queryKey: bankingQueryKeys.unmatchedTransactions(bankAccountId),
        queryFn: () => bankingService.getUnmatchedTransactions(bankAccountId, limit),
        staleTime: STALE_TIMES.transactions,
    });
}

/**
 * Transaktion aktualisieren (Notes, Tags)
 */
export function useUpdateTransaction() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, data }: { id: string; data: Parameters<typeof bankingService.updateTransaction>[1] }) =>
            bankingService.updateTransaction(id, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactionDetail(variables.id) });
        },
    });
}

/**
 * Monatliche Transaktionszusammenfassung
 */
export function useMonthlyTransactionSummary(bankAccountId?: string) {
    return useQuery({
        queryKey: bankingQueryKeys.monthlyTransactionSummary(bankAccountId),
        queryFn: () => bankingService.getMonthlyTransactionSummary(bankAccountId),
        staleTime: STALE_TIMES.stats,
    });
}

// ==================== Import Hooks ====================

/**
 * Unterstützte Import-Formate abrufen
 */
export function useSupportedFormats() {
    return useQuery({
        queryKey: bankingQueryKeys.supportedFormats(),
        queryFn: () => bankingService.getSupportedFormats(),
        staleTime: Infinity, // Formate ändern sich nie
    });
}

/**
 * Import-Vorschau erstellen
 */
export function useImportPreview() {
    return useMutation({
        mutationFn: ({ file, bankAccountId, formatHint }: { file: File; bankAccountId?: string; formatHint?: string }) =>
            bankingService.previewImport(file, bankAccountId, formatHint),
    });
}

/**
 * Import ausführen
 */
export function useExecuteImport() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ file, bankAccountId, formatHint }: { file: File; bankAccountId?: string; formatHint?: string }) =>
            bankingService.executeImport(file, bankAccountId, formatHint),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.accounts() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.import() });
        },
    });
}

/**
 * Import-Historie abrufen
 */
export function useImportHistory(bankAccountId?: string, limit = 20) {
    return useQuery({
        queryKey: bankingQueryKeys.importHistory(bankAccountId),
        queryFn: () => bankingService.getImportHistory(bankAccountId, limit),
        staleTime: STALE_TIMES.stats,
    });
}

// ==================== Payment Hooks ====================

/**
 * Zahlungsliste abrufen
 */
export function usePayments(params?: Parameters<typeof bankingService.getPayments>[0]) {
    return useQuery({
        queryKey: bankingQueryKeys.paymentList(params),
        queryFn: () => bankingService.getPayments(params),
        staleTime: STALE_TIMES.transactions,
    });
}

/**
 * Einzelne Zahlung abrufen
 */
export function usePayment(id: string, enabled = true) {
    return useQuery({
        queryKey: bankingQueryKeys.paymentDetail(id),
        queryFn: () => bankingService.getPayment(id),
        staleTime: STALE_TIMES.transactions,
        enabled: enabled && !!id,
    });
}

/**
 * Ausstehende Zahlungen abrufen
 */
export function usePendingPayments() {
    return useQuery({
        queryKey: bankingQueryKeys.pendingPayments(),
        queryFn: () => bankingService.getPendingPayments(),
        staleTime: STALE_TIMES.transactions,
    });
}

/**
 * Zahlung erstellen
 */
export function useCreatePayment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: bankingService.createPayment,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.payments() });
        },
    });
}

/**
 * Zahlung genehmigen
 */
export function useApprovePayment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: bankingService.approvePayment,
        onSuccess: (_, id) => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.payments() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.paymentDetail(id) });
        },
    });
}

/**
 * Zahlung stornieren
 */
export function useCancelPayment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
            bankingService.cancelPayment(id, reason),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.payments() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.paymentDetail(variables.id) });
        },
    });
}

/**
 * Zahlung einreichen (TAN-Challenge)
 */
export function useSubmitPayment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: bankingService.submitPayment,
        onSuccess: (_, id) => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.paymentDetail(id) });
        },
    });
}

/**
 * TAN bestätigen
 */
export function useConfirmPaymentTAN() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, tan }: { id: string; tan: string }) =>
            bankingService.confirmPaymentTAN(id, tan),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.payments() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.paymentDetail(variables.id) });
        },
    });
}

/**
 * Verfügbare TAN-Methoden abrufen
 */
export function useTANMethods() {
    return useQuery({
        queryKey: bankingQueryKeys.tanMethods(),
        queryFn: () => bankingService.getTANMethods(),
        staleTime: Infinity, // TAN-Methoden ändern sich selten
    });
}

// ==================== Skonto Hooks ====================

/**
 * Skonto-Opportunities abrufen
 */
export function useSkontoOpportunities(params?: { days_ahead?: number; include_expired?: boolean }) {
    const daysAhead = params?.days_ahead ?? 14;
    return useQuery({
        queryKey: bankingQueryKeys.skontoOpportunities(daysAhead),
        queryFn: () => bankingService.getSkontoOpportunities(daysAhead),
        staleTime: STALE_TIMES.dunning,
    });
}

// ==================== Additional Reconciliation Hooks ====================

/**
 * Match-Vorschläge mit Filterparametern
 */
export function useMatchSuggestionsFiltered(params?: { bank_account_id?: string; limit?: number }) {
    return useQuery({
        queryKey: [...bankingQueryKeys.reconciliation(), 'suggestions-filtered', params],
        queryFn: async () => {
            // Get unmatched transactions and for each get suggestions
            const unmatchedTx = await bankingService.getUnmatchedTransactions(
                params?.bank_account_id,
                params?.limit ?? 10
            );
            // For now, return empty array - the UI will handle this differently
            return unmatchedTx.map((tx) => ({
                id: tx.id,
                transaction: tx,
                document: null,
                confidence_score: 0,
                match_type: 'none',
            }));
        },
        staleTime: STALE_TIMES.transactions,
        enabled: true,
    });
}

/**
 * Abgleich starten (Batch)
 */
export function useRunReconciliation() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (bankAccountId?: string) =>
            bankingService.batchReconcile({ bank_account_id: bankAccountId }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.reconciliation() });
        },
    });
}

/**
 * Match akzeptieren
 */
export function useAcceptMatch() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (suggestionId: string) => {
            // The suggestion ID contains transactionId_documentId
            const [transactionId, documentId] = suggestionId.split('_');
            return bankingService.manualMatch(transactionId, documentId);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.reconciliation() });
        },
    });
}

/**
 * Match ablehnen
 */
export function useRejectMatch() {
    const queryClient = useQueryClient();

    return useMutation({
        // suggestionId unused - rejection is local-only without API call
        mutationFn: async () => {
            // For now, just invalidate queries - rejection doesn't need an API call
            // In a full implementation, this would mark the suggestion as rejected
            return Promise.resolve();
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.reconciliation() });
        },
    });
}

/**
 * Nicht-verknüpfte Dokumente abrufen
 */
export function useUnmatchedDocuments() {
    return useQuery({
        queryKey: [...bankingQueryKeys.reconciliation(), 'unmatched-documents'],
        queryFn: async () => {
            // This would need a backend endpoint - for now return empty array
            // In a full implementation: return bankingService.getUnmatchedDocuments()
            return [] as Array<{
                id: string;
                vendor_name: string | null;
                invoice_number: string | null;
                invoice_date: string | null;
                total_amount: number;
                currency: string | null;
            }>;
        },
        staleTime: STALE_TIMES.transactions,
    });
}

// ==================== Enhanced Reconciliation Hooks (New API) ====================

/**
 * Query Keys für erweiterte Reconciliation API
 */
export const enhancedReconciliationQueryKeys = {
    stats: (bankAccountId?: string) =>
        [...bankingQueryKeys.reconciliation(), 'stats', bankAccountId] as const,
    unmatchedEnhanced: (params?: Record<string, unknown>) =>
        [...bankingQueryKeys.reconciliation(), 'unmatched-enhanced', params] as const,
    suggestionsEnhanced: (transactionId: string) =>
        [...bankingQueryKeys.reconciliation(), 'suggestions-enhanced', transactionId] as const,
};

/**
 * Reconciliation-Statistiken abrufen
 */
export function useReconciliationStats(bankAccountId?: string) {
    return useQuery({
        queryKey: enhancedReconciliationQueryKeys.stats(bankAccountId),
        queryFn: () => bankingService.getReconciliationStats(bankAccountId),
        staleTime: STALE_TIMES.stats,
    });
}

/**
 * Unabgeglichene Transaktionen mit erweiterten Infos
 */
export function useUnmatchedTransactionsEnhanced(params?: {
    bank_account_id?: string;
    min_amount?: number;
    max_amount?: number;
    days_old?: number;
    sort_by?: 'booking_date' | 'amount' | 'counterparty';
    sort_order?: 'asc' | 'desc';
    offset?: number;
    limit?: number;
}) {
    return useQuery({
        queryKey: enhancedReconciliationQueryKeys.unmatchedEnhanced(params),
        queryFn: () => bankingService.getUnmatchedTransactionsEnhanced(params),
        staleTime: STALE_TIMES.transactions,
    });
}

/**
 * Erweiterte Match-Vorschläge für eine Transaktion
 */
export function useMatchSuggestionsEnhanced(
    transactionId: string,
    params?: { limit?: number; min_confidence?: number },
    enabled = true
) {
    return useQuery({
        queryKey: enhancedReconciliationQueryKeys.suggestionsEnhanced(transactionId),
        queryFn: () => bankingService.getMatchSuggestionsEnhanced(transactionId, params),
        staleTime: STALE_TIMES.transactions,
        enabled: enabled && !!transactionId,
    });
}

/**
 * Bulk Auto-Match durchführen
 */
export function useAutoMatchTransactions() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (params?: { bank_account_id?: string; min_confidence?: number; limit?: number }) =>
            bankingService.autoMatchTransactions(params),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.reconciliation() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.aging() });
        },
    });
}

/**
 * Manueller Abgleich mit erweiterten Optionen
 */
export function useCreateManualMatch() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({
            transactionId,
            data,
        }: {
            transactionId: string;
            data: {
                document_id: string;
                notes?: string;
                is_partial?: boolean;
                allocated_amount?: number;
            };
        }) => bankingService.createManualMatch(transactionId, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.transactions() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.reconciliation() });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.aging() });
        },
    });
}

/**
 * Match-Vorschlag ablehnen
 */
export function useRejectMatchEnhanced() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({
            transactionId,
            documentId,
            reason,
            neverSuggestAgain = false,
        }: {
            transactionId: string;
            documentId: string;
            reason: string;
            neverSuggestAgain?: boolean;
        }) =>
            bankingService.rejectMatch(transactionId, documentId, {
                reason,
                never_suggest_again: neverSuggestAgain,
            }),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({
                queryKey: enhancedReconciliationQueryKeys.suggestionsEnhanced(variables.transactionId),
            });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.reconciliation() });
        },
    });
}

// ==================== Erweitertes Mahnungswesen (BGB §286) Hooks ====================

// Query Keys für erweitertes Mahnungswesen
export const mahnungswesenQueryKeys = {
    // Mahn-Tasks
    mahnTasks: () => [...bankingQueryKeys.dunning(), 'mahn-tasks'] as const,
    mahnTaskList: (filters?: Record<string, unknown>) =>
        [...mahnungswesenQueryKeys.mahnTasks(), 'list', filters] as const,
    mahnTaskSummary: () =>
        [...mahnungswesenQueryKeys.mahnTasks(), 'summary'] as const,

    // Dunning History
    dunningHistory: (dunningId: string) =>
        [...bankingQueryKeys.dunning(), 'history', dunningId] as const,

    // Phone Calls
    phoneCalls: (dunningId: string) =>
        [...bankingQueryKeys.dunning(), 'phone-calls', dunningId] as const,

    // Mahnstopp
    dunningsWithMahnstopp: () =>
        [...bankingQueryKeys.dunning(), 'with-mahnstopp'] as const,

    // Verzugszinsen
    verzugszinsen: (dunningId: string) =>
        [...bankingQueryKeys.dunning(), 'verzugszinsen', dunningId] as const,

    // Stage Config
    dunningStages: () =>
        [...bankingQueryKeys.dunning(), 'stages'] as const,

    // Customer Overrides
    customerDunningSettings: (businessEntityId: string) =>
        [...bankingQueryKeys.dunning(), 'customer-settings', businessEntityId] as const,
};

// ==================== Mahn-Task Hooks ====================

/**
 * Mahnaufgaben auflisten
 */
export function useMahnTasks(params?: {
    task_type?: string;
    status?: string;
    assigned_user_id?: string;
    due_date_from?: string;
    due_date_to?: string;
    priority?: number;
    include_snoozed?: boolean;
    offset?: number;
    limit?: number;
}) {
    return useQuery({
        queryKey: mahnungswesenQueryKeys.mahnTaskList(params),
        queryFn: () => bankingService.getMahnTasks(params),
        staleTime: STALE_TIMES.dunning,
    });
}

/**
 * Mahnaufgaben-Zusammenfassung
 */
export function useMahnTaskSummary() {
    return useQuery({
        queryKey: mahnungswesenQueryKeys.mahnTaskSummary(),
        queryFn: () => bankingService.getMahnTaskSummary(),
        staleTime: STALE_TIMES.dunning,
    });
}

/**
 * Mahnaufgabe erstellen
 */
export function useCreateMahnTask() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: {
            dunning_record_id: string;
            task_type: string;
            due_date: string;
            assigned_user_id?: string;
            priority?: number;
        }) => bankingService.createMahnTask(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.mahnTasks() });
        },
    });
}

/**
 * Mahnaufgabe zuweisen
 */
export function useAssignMahnTask() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ taskId, assignedUserId }: { taskId: string; assignedUserId: string }) =>
            bankingService.assignMahnTask(taskId, assignedUserId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.mahnTasks() });
        },
    });
}

/**
 * Mahnaufgabe zurückstellen (max 3x)
 */
export function useSnoozeMahnTask() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ taskId, newDueDate, reason }: { taskId: string; newDueDate: string; reason?: string }) =>
            bankingService.snoozeMahnTask(taskId, newDueDate, reason),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.mahnTasks() });
        },
    });
}

/**
 * Mahnaufgabe abschließen
 */
export function useCompleteMahnTask() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ taskId, outcome, notes }: { taskId: string; outcome?: string; notes?: string }) =>
            bankingService.completeMahnTask(taskId, outcome, notes),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.mahnTasks() });
        },
    });
}

/**
 * Mehrere Mahnaufgaben abschließen
 */
export function useBulkCompleteMahnTasks() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ taskIds, notes }: { taskIds: string[]; notes?: string }) =>
            bankingService.bulkCompleteMahnTasks(taskIds, notes),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.mahnTasks() });
        },
    });
}

// ==================== Dunning History Hooks ====================

/**
 * Mahnung-Historie abrufen (Audit-Log)
 */
export function useDunningHistory(dunningId: string, enabled = true) {
    return useQuery({
        queryKey: mahnungswesenQueryKeys.dunningHistory(dunningId),
        queryFn: () => bankingService.getDunningHistory(dunningId),
        staleTime: STALE_TIMES.dunning,
        enabled: enabled && !!dunningId,
    });
}

// ==================== Mahnstopp Hooks ====================

/**
 * Mahnstopp setzen
 */
export function useSetMahnstopp() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ dunningId, reason, until }: { dunningId: string; reason: string; until?: string }) =>
            bankingService.setMahnstopp(dunningId, reason, until),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

/**
 * Mahnstopp aufheben
 * Akzeptiert entweder einen String (dunningId) oder ein Objekt { dunningId, notes }
 */
export function useLiftMahnstopp() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (params: string | { dunningId: string; notes?: string }) => {
            const dunningId = typeof params === 'string' ? params : params.dunningId;
            const notes = typeof params === 'string' ? undefined : params.notes;
            return bankingService.liftMahnstopp(dunningId, notes);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

/**
 * Mahnvorgänge mit Mahnstopp abrufen
 */
export function useDunningsWithMahnstopp() {
    return useQuery({
        queryKey: mahnungswesenQueryKeys.dunningsWithMahnstopp(),
        queryFn: () => bankingService.getDunningsWithMahnstopp(),
        staleTime: STALE_TIMES.dunning,
    });
}

// ==================== B2B/B2C und Pauschale Hooks ====================

/**
 * B2B-Status setzen
 */
export function useSetB2BStatus() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ dunningId, isB2B }: { dunningId: string; isB2B: boolean }) =>
            bankingService.setB2BStatus(dunningId, isB2B),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

/**
 * B2B-Pauschale (EUR 40) beanspruchen
 */
export function useClaimB2BPauschale() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (dunningId: string) => bankingService.claimB2BPauschale(dunningId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

/**
 * Verzugszinsen berechnen
 */
export function useVerzugszinsen(dunningId: string, asOfDate?: string, enabled = true) {
    return useQuery({
        queryKey: mahnungswesenQueryKeys.verzugszinsen(dunningId),
        queryFn: () => bankingService.calculateVerzugszinsen(dunningId, asOfDate),
        staleTime: STALE_TIMES.dunning,
        enabled: enabled && !!dunningId,
    });
}

// ==================== Telefonprotokoll Hooks ====================

/**
 * Telefonkontakte zu Mahnvorgang abrufen
 */
export function usePhoneCalls(dunningId: string, enabled = true) {
    return useQuery({
        queryKey: mahnungswesenQueryKeys.phoneCalls(dunningId),
        queryFn: () => bankingService.getPhoneCalls(dunningId),
        staleTime: STALE_TIMES.dunning,
        enabled: enabled && !!dunningId,
    });
}

/**
 * Telefonkontakt protokollieren
 */
export function useLogPhoneCall() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ dunningId, data }: { dunningId: string; data: Parameters<typeof bankingService.logPhoneCall>[1] }) =>
            bankingService.logPhoneCall(dunningId, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.phoneCalls(variables.dunningId) });
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.dunningHistory(variables.dunningId) });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

// ==================== Bulk Action Hooks ====================

/**
 * Mehrere Mahnvorgänge eskalieren
 */
export function useBulkEscalateDunnings() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ dunningIds, notes }: { dunningIds: string[]; notes?: string }) =>
            bankingService.bulkEscalateDunnings(dunningIds, notes),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

/**
 * Mahnungen für mehrere Vorgänge versenden
 */
export function useBulkSendReminders() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ dunningIds, channel, notes }: {
            dunningIds: string[];
            channel?: 'email' | 'letter' | 'both';
            notes?: string;
        }) => bankingService.bulkSendReminders(dunningIds, { channel, notes }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

// ==================== Dunning Stage Config Hooks (Admin) ====================

/**
 * Mahnstufen-Konfiguration abrufen
 */
export function useDunningStages() {
    return useQuery({
        queryKey: mahnungswesenQueryKeys.dunningStages(),
        queryFn: () => bankingService.getDunningStages(),
        staleTime: STALE_TIMES.stats, // Admin-Einstellungen ändern sich selten
    });
}

/**
 * Mahnstufe erstellen
 */
export function useCreateDunningStage() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: Parameters<typeof bankingService.createDunningStage>[0]) =>
            bankingService.createDunningStage(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.dunningStages() });
        },
    });
}

/**
 * Mahnstufe aktualisieren
 */
export function useUpdateDunningStage() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ stageId, data }: { stageId: string; data: Parameters<typeof bankingService.updateDunningStage>[1] }) =>
            bankingService.updateDunningStage(stageId, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.dunningStages() });
        },
    });
}

/**
 * Mahnstufen neu ordnen (Drag-and-Drop)
 */
export function useReorderDunningStages() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (stageIds: string[]) => bankingService.reorderDunningStages(stageIds),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.dunningStages() });
        },
    });
}

// ==================== Customer Dunning Override Hooks ====================

/**
 * Kundenspezifische Mahneinstellungen abrufen
 */
export function useCustomerDunningSettings(businessEntityId: string, enabled = true) {
    return useQuery({
        queryKey: mahnungswesenQueryKeys.customerDunningSettings(businessEntityId),
        queryFn: () => bankingService.getCustomerDunningSettings(businessEntityId),
        staleTime: STALE_TIMES.stats,
        enabled: enabled && !!businessEntityId,
    });
}

/**
 * Kundenspezifische Mahneinstellungen setzen
 */
export function useSetCustomerDunningSettings() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ businessEntityId, data }: { businessEntityId: string; data: Parameters<typeof bankingService.setCustomerDunningSettings>[1] }) =>
            bankingService.setCustomerDunningSettings(businessEntityId, data),
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.customerDunningSettings(variables.businessEntityId) });
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
        },
    });
}

// ==================== Dunning Records Hook ====================

/**
 * Alle Mahnvorgänge auflisten
 */
export function useDunningRecords(params?: {
    status?: string;
    mahnstopp?: boolean;
    dunning_level?: number;
    is_b2b?: boolean;
    business_entity_id?: string;
    offset?: number;
    limit?: number;
}) {
    return useQuery({
        queryKey: [...bankingQueryKeys.dunning(), 'records', params],
        queryFn: async () => {
            const result = await bankingService.getDunningRecords(params);
            return result;
        },
        staleTime: STALE_TIMES.dunning,
    });
}

// ==================== Dunning Stage Config Aliases ====================

/**
 * Mahnstufen-Konfiguration abrufen (Alias)
 */
export function useDunningStageConfigs() {
    return useDunningStages();
}

/**
 * Mahnstufe aktualisieren (Alias mit alternativer Signatur)
 */
export function useUpdateDunningStageConfig() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ configId, data }: {
            configId: string;
            data: {
                days_after_previous?: number;
                fee_amount?: number;
                communication_channel?: string;
                auto_escalate?: boolean;
                requires_approval?: boolean;
            };
        }) => bankingService.updateDunningStage(configId, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: mahnungswesenQueryKeys.dunningStages() });
        },
    });
}

// ==================== Liquidity Forecast Hooks ====================

/**
 * Liquiditätsprognose abrufen (30/60/90 Tage)
 */
export function useLiquidityForecast(params?: {
    bank_account_id?: string;
    starting_balance?: number;
}) {
    return useQuery({
        queryKey: bankingQueryKeys.liquidityForecast(params?.bank_account_id),
        queryFn: () => bankingService.getLiquidityForecast(params),
        staleTime: STALE_TIMES.cashflow,
    });
}

/**
 * Engpass-Vorhersage abrufen
 */
export function useLiquidityBottlenecks(params?: {
    bank_account_id?: string;
    days_ahead?: number;
    min_severity?: 'healthy' | 'adequate' | 'caution' | 'warning' | 'critical';
}) {
    return useQuery({
        queryKey: bankingQueryKeys.liquidityBottlenecks({
            bankAccountId: params?.bank_account_id,
            daysAhead: params?.days_ahead,
        }),
        queryFn: () => bankingService.getLiquidityBottlenecks(params),
        staleTime: STALE_TIMES.cashflow,
    });
}

/**
 * Wasserfall-Chart-Daten abrufen
 */
export function useWaterfallChart(params?: {
    bank_account_id?: string;
    days?: number;
    granularity?: 'daily' | 'weekly' | 'monthly';
}) {
    return useQuery({
        queryKey: bankingQueryKeys.liquidityWaterfall({
            bankAccountId: params?.bank_account_id,
            days: params?.days,
            granularity: params?.granularity,
        }),
        queryFn: () => bankingService.getWaterfallChart(params),
        staleTime: STALE_TIMES.cashflow,
    });
}

/**
 * Zahlungsanomalien erkennen
 */
export function usePaymentAnomalies(params?: {
    bank_account_id?: string;
    days_back?: number;
    min_confidence?: number;
}) {
    return useQuery({
        queryKey: bankingQueryKeys.liquidityAnomalies({
            bankAccountId: params?.bank_account_id,
            daysBack: params?.days_back,
        }),
        queryFn: () => bankingService.detectPaymentAnomalies(params),
        staleTime: STALE_TIMES.cashflow,
    });
}

// ==================== Auto-Mahnlauf Hooks ====================

/**
 * Query Keys für Auto-Mahnlauf
 */
export const autoMahnlaufQueryKeys = {
    autoDunning: () => [...bankingQueryKeys.dunning(), 'auto'] as const,
    autoDunningSettings: () => [...autoMahnlaufQueryKeys.autoDunning(), 'settings'] as const,
    autoDunningPreview: () => [...autoMahnlaufQueryKeys.autoDunning(), 'preview'] as const,
};

/**
 * Auto-Mahnlauf-Einstellungen abrufen
 */
export function useAutoDunningSettings() {
    return useQuery({
        queryKey: autoMahnlaufQueryKeys.autoDunningSettings(),
        queryFn: () => bankingService.getAutoDunningSettings(),
        staleTime: STALE_TIMES.stats,
    });
}

/**
 * Auto-Mahnlauf-Einstellungen aktualisieren
 */
export function useUpdateAutoDunningSettings() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (settings: Parameters<typeof bankingService.updateAutoDunningSettings>[0]) =>
            bankingService.updateAutoDunningSettings(settings),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: autoMahnlaufQueryKeys.autoDunningSettings() });
        },
    });
}

/**
 * Automatischen Mahnlauf-Vorschau abrufen (dry_run = true)
 */
export function useAutoDunningPreview() {
    return useQuery({
        queryKey: autoMahnlaufQueryKeys.autoDunningPreview(),
        queryFn: () => bankingService.processAutomaticDunning(true),
        staleTime: STALE_TIMES.dunning,
    });
}

/**
 * Automatischen Mahnlauf ausführen
 */
export function useProcessAutomaticDunning() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (dryRun: boolean) => bankingService.processAutomaticDunning(dryRun),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: bankingQueryKeys.dunning() });
            queryClient.invalidateQueries({ queryKey: autoMahnlaufQueryKeys.autoDunning() });
        },
    });
}
