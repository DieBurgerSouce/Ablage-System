import { apiClient } from '../client';

// Import Union Types from models
import type {
    CurrencyCode,
    MahnTaskType,
    MahnTaskStatus,
    PhoneCallOutcome,
    DunningActionType,
    MahnungHistoryActionType,
    DunningLevelNumber,
    MahnungHistoryEntry,
} from '@/types/models/banking';

// ==================== Types ====================

// Cash-Flow Types
export interface CashFlowForecast {
    period: {
        start: string;
        end: string;
        scenario: 'optimistic' | 'realistic' | 'pessimistic';
    };
    totals: {
        inflow: number;
        outflow: number;
        net: number;
    };
    risk: {
        min_balance: number;
        min_balance_date: string | null;
        days_negative: number;
    };
    entries_count: number;
}

export interface CashFlowSummary {
    current_balance: number;
    short_term: {
        days: number;
        inflow: number;
        outflow: number;
        net: number;
        ending_balance: number;
    };
    medium_term: {
        days: number;
        inflow: number;
        outflow: number;
        net: number;
        ending_balance: number;
    };
    long_term: {
        days: number;
        inflow: number;
        outflow: number;
        net: number;
        ending_balance: number;
    };
    warnings: string[];
}

export interface DailyCashFlowEntry {
    date: string;
    inflow: number;
    outflow: number;
    net: number;
    cumulative: number;
}

export interface CashFlowScenario {
    scenario: string;
    total_inflow: number;
    total_outflow: number;
    net_flow: number;
    min_balance: number;
    days_negative: number;
}

export interface ScenarioComparison {
    optimistic: CashFlowScenario;
    realistic: CashFlowScenario;
    pessimistic: CashFlowScenario;
}

// Dunning Types
export interface DunningStats {
    total_active: number;
    by_level: Record<number, number>;
    total_amount_overdue: number;
    total_fees: number;
    total_interest: number;
    avg_days_overdue: number;
    success_rate_30d: number;
    /** Anzahl Mahnvorgaenge mit aktivem Mahnstopp */
    mahnstopp_count?: number;
}

export interface OverdueInvoice {
    document_id: string;
    invoice_number: string;
    creditor_name: string;
    amount: number;
    due_date: string;
    days_overdue: number;
    current_level: string;
    recommended_action: string;
    accumulated_fees: number;
    late_interest: number;
    total_due: number;
}

// Aging Types
export interface AgingBucket {
    bucket: string;
    count: number;
    amount: number;
    percentage: number;
}

export interface AgingLineItem {
    document_id: string;
    invoice_number: string;
    counterparty: string;
    due_date: string | null;
    amount: number;
    bucket: string;
    days_overdue: number;
}

export interface AgingReport {
    report_type: 'receivables' | 'payables';
    as_of_date: string;
    generated_at: string;
    summary: {
        total_count: number;
        total_amount: number;
        total_overdue: number;
        average_days_overdue: number;
    };
    buckets: AgingBucket[];
    line_items: AgingLineItem[];
}

export interface AgingSummary {
    receivables: {
        total_count: number;
        total_amount: number;
        total_overdue: number;
        buckets: AgingBucket[];
    };
    payables: {
        total_count: number;
        total_amount: number;
        total_overdue: number;
        buckets: AgingBucket[];
    };
    net_position: number;
}

export interface TopDebtor {
    counterparty: string;
    total_amount: number;
    invoice_count: number;
    oldest_due_date: string | null;
    avg_days_overdue: number;
}

export interface DSO {
    dso: number;
    period_days: number;
    revenue: number;
    avg_receivables: number;
    interpretation: string;
    trend?: {
        previous_dso: number;
        change: number;
    };
}

// Transaction Types
export interface TransactionStats {
    total_count: number;
    total_inflow: number;
    total_outflow: number;
    matched_count: number;
    unmatched_count: number;
    match_rate: number;
    avg_transaction_amount: number;
}

// Account Types
export interface BankAccountWithStats {
    id: string;
    name: string;
    iban: string;
    bank_name: string | null;
    currency: string;
    is_active: boolean;
    transaction_count: number;
    last_import_date: string | null;
    balance: number | null;
    unmatched_count: number;
}

export interface BankAccount {
    id: string;
    user_id: string;
    account_name: string;
    iban: string;
    bic: string | null;
    bank_name: string | null;
    account_holder: string | null;
    account_type: 'checking' | 'savings' | 'business' | 'credit';
    currency: string;
    is_active: boolean;
    connection_status: string;
    current_balance: number | null;
    balance_date: string | null;
    last_sync_at: string | null;
    auto_sync_enabled: boolean;
    created_at: string;
    updated_at: string;
}

export interface BankAccountCreate {
    account_name: string;
    iban: string;
    bic?: string;
    bank_name?: string;
    account_holder?: string;
    account_type?: 'checking' | 'savings' | 'business' | 'credit';
    currency?: string;
}

export interface BankAccountUpdate {
    account_name?: string;
    bank_name?: string;
    account_holder?: string;
    account_type?: 'checking' | 'savings' | 'business' | 'credit';
    is_active?: boolean;
    auto_sync_enabled?: boolean;
}

// Transaction Types (Extended)
export type ReconciliationStatus = 'unmatched' | 'matched' | 'partial' | 'manual' | 'ignored';
export type TransactionType = 'transfer' | 'direct_debit' | 'card' | 'cash' | 'fee' | 'interest' | 'other';

export interface BankTransaction {
    id: string;
    bank_account_id: string;
    transaction_id: string | null;
    booking_date: string;
    value_date: string;
    amount: number;
    currency: string;
    counterparty_name: string | null;
    counterparty_iban: string | null;
    counterparty_bic: string | null;
    reference_text: string | null;
    transaction_type: TransactionType | null;
    booking_text: string | null;
    reconciliation_status: ReconciliationStatus;
    matched_document_id: string | null;
    matched_invoice_number: string | null;
    match_confidence: number | null;
    match_method: string | null;
    is_partial_payment: boolean;
    allocated_amount: number | null;
    remaining_amount: number | null;
    imported_at: string;
}

export interface TransactionFilter {
    bank_account_id?: string;
    date_from?: string;
    date_to?: string;
    amount_min?: number;
    amount_max?: number;
    transaction_type?: TransactionType;
    reconciliation_status?: ReconciliationStatus;
    search?: string;
}

export interface TransactionListResponse {
    items: BankTransaction[];
    total: number;
    offset: number;
    limit: number;
}

export interface TransactionUpdate {
    notes?: string;
    tags?: string[];
    category?: string;
}

// Import Types
export type ImportFormat =
    | 'mt940'
    | 'camt053'
    | 'csv_generic'
    | 'csv_sparkasse'
    | 'csv_volksbank'
    | 'csv_deutsche_bank'
    | 'csv_commerzbank'
    | 'csv_ing'
    | 'csv_n26'
    | 'csv_dkb'
    | 'pdf';

export interface ImportPreview {
    format_detected: ImportFormat;
    format_confidence: number;
    transaction_count: number;
    date_from: string | null;
    date_to: string | null;
    total_credits: number;
    total_debits: number;
    sample_transactions: Record<string, unknown>[];
    warnings: string[];
}

export interface ImportResponse {
    id: string;
    filename: string | null;
    format: ImportFormat;
    format_variant: string | null;
    status: string;
    transaction_count: number;
    duplicate_count: number;
    error_count: number;
    date_from: string | null;
    date_to: string | null;
    imported_at: string;
    processing_duration_ms: number | null;
    errors: Record<string, unknown>[];
}

export interface SupportedFormat {
    format: ImportFormat;
    name: string;
    description: string;
    extensions: string[];
}

// Reconciliation Types
export interface MatchCandidate {
    document_id: string;
    invoice_number: string | null;
    invoice_date: string | null;
    due_date: string | null;
    gross_amount: number;
    counterparty_name: string | null;
    counterparty_iban: string | null;
    confidence: number;
    match_method: string;
    match_details: Record<string, unknown>;
}

export interface ReconciliationResult {
    transaction_id: string;
    status: ReconciliationStatus;
    matched_document_id: string | null;
    match_confidence: number | null;
    match_method: string | null;
}

export interface BatchReconciliationResult {
    total_processed: number;
    matched_count: number;
    partial_count: number;
    unmatched_count: number;
    match_rate: number;
    results: ReconciliationResult[];
}

export interface SplitItem {
    document_id: string;
    amount: number;
}

// Payment Types
export type PaymentStatus =
    | 'draft'
    | 'pending_approval'
    | 'approved'
    | 'pending_tan'
    | 'submitted'
    | 'executed'
    | 'failed'
    | 'cancelled';

export type PaymentType = 'transfer' | 'direct_debit' | 'batch';
export type SEPAType = 'pain_001' | 'pain_008';

export interface PaymentOrder {
    id: string;
    user_id: string;
    bank_account_id: string;
    document_id: string | null;
    invoice_number: string | null;
    payment_type: PaymentType;
    sepa_type: SEPAType | null;
    beneficiary_name: string;
    beneficiary_iban: string;
    beneficiary_bic: string | null;
    amount: number;
    currency: string;
    reference: string | null;
    execution_date: string | null;
    status: PaymentStatus;
    tan_required: boolean;
    uses_skonto: boolean;
    skonto_amount: number | null;
    original_amount: number | null;
    skonto_deadline: string | null;
    approved_at: string | null;
    submitted_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface PaymentOrderCreate {
    bank_account_id: string;
    document_id?: string;
    beneficiary_name: string;
    beneficiary_iban: string;
    beneficiary_bic?: string;
    amount: number;
    currency?: string;
    reference?: string;
    execution_date?: string;
    use_skonto?: boolean;
}

export interface PaymentListResponse {
    payments: PaymentOrder[];
    total: number;
    offset: number;
    limit: number;
}

export interface TANChallenge {
    session_id: string;
    challenge_text: string;
    tan_method: string;
    expires_at: string;
}

export interface TANMethod {
    id: string;
    name: string;
    type: 'pushTAN' | 'photoTAN' | 'chipTAN' | 'smsTAN' | 'appTAN';
    description: string;
}

// Skonto Types
export interface SkontoOpportunity {
    document_id: string;
    invoice_number: string | null;
    invoice_date: string | null;
    due_date: string | null;
    days_until_due: number;
    gross_amount: number;
    currency: string;
    beneficiary_name: string | null;
    beneficiary_iban: string | null;
    has_skonto: boolean;
    skonto_percent: number | null;
    skonto_deadline: string | null;
    skonto_amount: number | null;
    amount_with_skonto: number | null;
    skonto_days_remaining: number | null;
}

// ==================== Banking Service ====================

export const bankingService = {
    // ==================== Cash-Flow ====================

    getCashFlowForecast: async (params?: {
        days_ahead?: number;
        scenario?: 'optimistic' | 'realistic' | 'pessimistic';
        bank_account_id?: string;
    }) => {
        const response = await apiClient.get<CashFlowForecast>('/banking/cashflow/forecast', { params });
        return response.data;
    },

    getCashFlowSummary: async (params?: { bank_account_id?: string }) => {
        const response = await apiClient.get<CashFlowSummary>('/banking/cashflow/summary', { params });
        return response.data;
    },

    getCashFlowDaily: async (params?: { days?: number; bank_account_id?: string }) => {
        const response = await apiClient.get<DailyCashFlowEntry[]>('/banking/cashflow/daily', { params });
        return response.data;
    },

    getCashFlowScenarios: async (params?: { days_ahead?: number; bank_account_id?: string }) => {
        const response = await apiClient.get<ScenarioComparison>('/banking/cashflow/scenarios', { params });
        return response.data;
    },

    // ==================== Dunning ====================

    /**
     * Alle Mahnvorgänge auflisten mit optionalen Filtern
     */
    getDunningRecords: async (params?: {
        status?: string;
        mahnstopp?: boolean;
        dunning_level?: number;
        is_b2b?: boolean;
        business_entity_id?: string;
        offset?: number;
        limit?: number;
    }): Promise<{ items: DunningRecord[]; total: number; offset: number; limit: number }> => {
        const response = await apiClient.get<{ items: DunningRecord[]; total: number; offset: number; limit: number }>(
            '/banking/dunning',
            { params }
        );
        return response.data;
    },

    getDunningStats: async () => {
        const response = await apiClient.get<DunningStats>('/banking/dunning/stats');
        return response.data;
    },

    getOverdueInvoices: async (params?: { min_days?: number; max_days?: number }) => {
        const response = await apiClient.get<OverdueInvoice[]>('/banking/dunning/overdue', { params });
        return response.data;
    },

    createDunning: async (params: { document_id: string; level?: string; notes?: string }) => {
        const response = await apiClient.post('/banking/dunning', null, { params });
        return response.data;
    },

    escalateDunning: async (dunningId: string, notes?: string) => {
        const response = await apiClient.post(`/banking/dunning/${dunningId}/escalate`, null, { params: { notes } });
        return response.data;
    },

    closeDunning: async (dunningId: string, status: string, notes?: string) => {
        const response = await apiClient.post(`/banking/dunning/${dunningId}/close`, null, { params: { status, notes } });
        return response.data;
    },

    // ==================== Aging ====================

    getAgingSummary: async () => {
        const response = await apiClient.get<AgingSummary>('/banking/aging/summary');
        return response.data;
    },

    getReceivablesAging: async (params?: { as_of_date?: string; counterparty?: string }) => {
        const response = await apiClient.get<AgingReport>('/banking/aging/receivables', { params });
        return response.data;
    },

    getPayablesAging: async (params?: { as_of_date?: string; counterparty?: string }) => {
        const response = await apiClient.get<AgingReport>('/banking/aging/payables', { params });
        return response.data;
    },

    getTopDebtors: async (limit = 10) => {
        const response = await apiClient.get<TopDebtor[]>('/banking/aging/top-debtors', { params: { limit } });
        return response.data;
    },

    getTopCreditors: async (limit = 10) => {
        const response = await apiClient.get<TopDebtor[]>('/banking/aging/top-creditors', { params: { limit } });
        return response.data;
    },

    getDSO: async (periodDays = 90) => {
        const response = await apiClient.get<DSO>('/banking/aging/dso', { params: { period_days: periodDays } });
        return response.data;
    },

    // ==================== Transactions ====================

    getTransactionStats: async (params?: { bank_account_id?: string; date_from?: string; date_to?: string }) => {
        const response = await apiClient.get<TransactionStats>('/banking/transactions/stats', { params });
        return response.data;
    },

    // ==================== Accounts ====================

    getAccountsWithStats: async () => {
        const response = await apiClient.get<BankAccountWithStats[]>('/banking/accounts/with-stats');
        return response.data;
    },

    // ==================== Reconciliation ====================

    batchReconcile: async (params?: { bank_account_id?: string; limit?: number }) => {
        const response = await apiClient.post<BatchReconciliationResult>('/banking/reconciliation/batch', null, { params });
        return response.data;
    },

    getMatchSuggestions: async (transactionId: string, limit = 5) => {
        const response = await apiClient.get<MatchCandidate[]>(`/banking/reconciliation/suggestions/${transactionId}`, { params: { limit } });
        return response.data;
    },

    manualMatch: async (transactionId: string, documentId: string, notes?: string) => {
        const response = await apiClient.post<ReconciliationResult>(`/banking/reconciliation/match/${transactionId}`, { document_id: documentId, notes });
        return response.data;
    },

    unmatchTransaction: async (transactionId: string) => {
        await apiClient.post(`/banking/reconciliation/unmatch/${transactionId}`);
    },

    splitTransaction: async (transactionId: string, splits: SplitItem[]) => {
        const response = await apiClient.post<ReconciliationResult[]>(`/banking/reconciliation/split/${transactionId}`, { splits });
        return response.data;
    },

    autoReconcileSingle: async (transactionId: string) => {
        const response = await apiClient.post<{ matched: boolean; document_id?: string; confidence?: number }>(`/banking/reconciliation/auto/${transactionId}`);
        return response.data;
    },

    // ==================== Accounts (Extended) ====================

    getAccounts: async (includeInactive = false) => {
        const response = await apiClient.get<BankAccount[]>('/banking/accounts', { params: { include_inactive: includeInactive } });
        return response.data;
    },

    getAccount: async (id: string) => {
        const response = await apiClient.get<BankAccount>(`/banking/accounts/${id}`);
        return response.data;
    },

    createAccount: async (data: BankAccountCreate) => {
        const response = await apiClient.post<BankAccount>('/banking/accounts', data);
        return response.data;
    },

    updateAccount: async (id: string, data: BankAccountUpdate) => {
        const response = await apiClient.put<BankAccount>(`/banking/accounts/${id}`, data);
        return response.data;
    },

    deleteAccount: async (id: string) => {
        await apiClient.delete(`/banking/accounts/${id}`);
    },

    // ==================== Transactions (Extended) ====================

    getTransactions: async (params: TransactionFilter & { offset?: number; limit?: number }) => {
        const response = await apiClient.get<TransactionListResponse>('/banking/transactions', { params });
        return response.data;
    },

    getTransaction: async (id: string) => {
        const response = await apiClient.get<BankTransaction>(`/banking/transactions/${id}`);
        return response.data;
    },

    getUnmatchedTransactions: async (bankAccountId?: string, limit = 50) => {
        const response = await apiClient.get<BankTransaction[]>('/banking/transactions/unmatched', {
            params: { bank_account_id: bankAccountId, limit },
        });
        return response.data;
    },

    updateTransaction: async (id: string, data: TransactionUpdate) => {
        const response = await apiClient.patch<BankTransaction>(`/banking/transactions/${id}`, data);
        return response.data;
    },

    getMonthlyTransactionSummary: async (bankAccountId?: string) => {
        const response = await apiClient.get<{ month: string; count: number; credits: number; debits: number }[]>(
            '/banking/transactions/monthly',
            { params: { bank_account_id: bankAccountId } }
        );
        return response.data;
    },

    // ==================== Import ====================

    getSupportedFormats: async () => {
        const response = await apiClient.get<SupportedFormat[]>('/banking/import/formats');
        return response.data;
    },

    previewImport: async (file: File, bankAccountId?: string, formatHint?: string) => {
        const formData = new FormData();
        formData.append('file', file);
        if (bankAccountId) formData.append('bank_account_id', bankAccountId);
        if (formatHint) formData.append('format', formatHint);

        const response = await apiClient.post<ImportPreview>('/banking/import/preview', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
        return response.data;
    },

    executeImport: async (file: File, bankAccountId?: string, formatHint?: string) => {
        const formData = new FormData();
        formData.append('file', file);
        if (bankAccountId) formData.append('bank_account_id', bankAccountId);
        if (formatHint) formData.append('format', formatHint);

        const response = await apiClient.post<ImportResponse>('/banking/import', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
        return response.data;
    },

    getImportHistory: async (bankAccountId?: string, limit = 20) => {
        const response = await apiClient.get<ImportResponse[]>('/banking/import/history', {
            params: { bank_account_id: bankAccountId, limit },
        });
        return response.data;
    },

    // ==================== Payments ====================

    getPayments: async (params?: { bank_account_id?: string; status?: PaymentStatus; offset?: number; limit?: number }) => {
        const response = await apiClient.get<PaymentListResponse>('/banking/payments', { params });
        return response.data;
    },

    getPayment: async (id: string) => {
        const response = await apiClient.get<PaymentOrder>(`/banking/payments/${id}`);
        return response.data;
    },

    getPendingPayments: async () => {
        const response = await apiClient.get<PaymentOrder[]>('/banking/payments/pending');
        return response.data;
    },

    createPayment: async (data: PaymentOrderCreate) => {
        const response = await apiClient.post<PaymentOrder>('/banking/payments', data);
        return response.data;
    },

    approvePayment: async (id: string) => {
        const response = await apiClient.post<PaymentOrder>(`/banking/payments/${id}/approve`);
        return response.data;
    },

    cancelPayment: async (id: string, reason?: string) => {
        const response = await apiClient.post<PaymentOrder>(`/banking/payments/${id}/cancel`, null, { params: { reason } });
        return response.data;
    },

    submitPayment: async (id: string) => {
        const response = await apiClient.post<{ status: string; tan_challenge?: TANChallenge }>(`/banking/payments/${id}/submit`);
        return response.data;
    },

    confirmPaymentTAN: async (id: string, tan: string) => {
        const response = await apiClient.post<PaymentOrder>(`/banking/payments/${id}/confirm-tan`, null, { params: { tan } });
        return response.data;
    },

    getTANMethods: async () => {
        const response = await apiClient.get<TANMethod[]>('/banking/payments/tan/methods');
        return response.data;
    },

    // ==================== Skonto ====================

    getSkontoOpportunities: async (daysAhead = 14) => {
        const response = await apiClient.get<SkontoOpportunity[]>('/banking/payments/skonto-opportunities', {
            params: { days_ahead: daysAhead },
        });
        return response.data;
    },

    // ==================== Erweitertes Mahnungswesen (BGB §286) ====================

    // Mahn-Tasks
    getMahnTasks: async (params?: {
        task_type?: string;
        status?: string;
        assigned_user_id?: string;
        due_date_from?: string;
        due_date_to?: string;
        priority?: number;
        include_snoozed?: boolean;
        offset?: number;
        limit?: number;
    }) => {
        const response = await apiClient.get<{
            items: MahnTask[];
            total: number;
            offset: number;
            limit: number;
        }>('/banking/mahn-tasks', { params });
        return response.data;
    },

    getMahnTaskSummary: async () => {
        const response = await apiClient.get<MahnTaskSummary>('/banking/mahn-tasks/summary');
        return response.data;
    },

    createMahnTask: async (data: {
        dunning_record_id: string;
        task_type: string;
        due_date: string;
        assigned_user_id?: string;
        priority?: number;
    }) => {
        const response = await apiClient.post<MahnTask>('/banking/mahn-tasks', data);
        return response.data;
    },

    assignMahnTask: async (taskId: string, assignedUserId: string) => {
        const response = await apiClient.post<MahnTask>(`/banking/mahn-tasks/${taskId}/assign`, null, {
            params: { assigned_user_id: assignedUserId },
        });
        return response.data;
    },

    snoozeMahnTask: async (taskId: string, snoozeUntil: string, reason?: string) => {
        const response = await apiClient.post<MahnTask>(`/banking/mahn-tasks/${taskId}/snooze`, {
            snooze_until: snoozeUntil,
            reason,
        });
        return response.data;
    },

    completeMahnTask: async (taskId: string, outcome?: string, notes?: string) => {
        const response = await apiClient.post<MahnTask>(`/banking/mahn-tasks/${taskId}/complete`, { outcome, notes });
        return response.data;
    },

    bulkCompleteMahnTasks: async (taskIds: string[], notes?: string) => {
        const response = await apiClient.post<{
            total: number;
            completed: number;
            failed: number;
            errors: Array<{ task_id: string; error: string }>;
        }>('/banking/mahn-tasks/bulk-complete', { task_ids: taskIds, notes });
        return response.data;
    },

    // Mahnung History
    getDunningHistory: async (dunningId: string) => {
        const response = await apiClient.get<{
            items: MahnungHistoryEntry[];
            total: number;
        }>(`/banking/dunning/${dunningId}/history`);
        return response.data;
    },

    // Mahnstopp
    setMahnstopp: async (dunningId: string, reason: string, untilDate?: string) => {
        const response = await apiClient.post<DunningRecord>(`/banking/dunning/${dunningId}/mahnstopp`, {
            reason,
            until_date: untilDate,
        });
        return response.data;
    },

    liftMahnstopp: async (dunningId: string, notes?: string) => {
        const response = await apiClient.delete<DunningRecord>(`/banking/dunning/${dunningId}/mahnstopp`, {
            params: { notes },
        });
        return response.data;
    },

    getDunningsWithMahnstopp: async () => {
        const response = await apiClient.get<DunningRecord[]>('/banking/dunning/with-mahnstopp');
        return response.data;
    },

    // B2B/B2C Status und Pauschale
    setB2BStatus: async (dunningId: string, isB2B: boolean) => {
        const response = await apiClient.put<DunningRecord>(`/banking/dunning/${dunningId}/b2b-status`, null, {
            params: { is_b2b: isB2B },
        });
        return response.data;
    },

    claimB2BPauschale: async (dunningId: string) => {
        const response = await apiClient.post<B2BPauschaleClaimResponse>(`/banking/dunning/${dunningId}/b2b-pauschale`);
        return response.data;
    },

    // Verzugszinsen
    calculateVerzugszinsen: async (dunningId: string, asOfDate?: string) => {
        const response = await apiClient.get<VerzugszinsenCalculation>(`/banking/dunning/${dunningId}/verzugszinsen`, {
            params: { as_of_date: asOfDate },
        });
        return response.data;
    },

    // Telefonprotokoll
    logPhoneCall: async (dunningId: string, data: PhoneCallLogCreate) => {
        const response = await apiClient.post<PhoneCallLog>(`/banking/dunning/${dunningId}/phone-call`, data);
        return response.data;
    },

    getPhoneCalls: async (dunningId: string) => {
        const response = await apiClient.get<{
            items: PhoneCallLog[];
            total: number;
        }>(`/banking/dunning/${dunningId}/phone-calls`);
        return response.data;
    },

    // Bulk Actions
    bulkEscalateDunnings: async (dunningIds: string[], notes?: string) => {
        const response = await apiClient.post<BulkEscalateResponse>('/banking/dunning/bulk-escalate', {
            dunning_ids: dunningIds,
            notes,
        });
        return response.data;
    },

    /**
     * Mahnungen für mehrere Vorgänge versenden
     */
    bulkSendReminders: async (dunningIds: string[], options?: {
        channel?: 'email' | 'letter' | 'both';
        notes?: string;
    }): Promise<{
        total: number;
        sent: number;
        failed: number;
        errors: Array<{ dunning_id: string; error: string }>;
    }> => {
        const response = await apiClient.post('/banking/dunning/bulk-send-reminders', {
            dunning_ids: dunningIds,
            channel: options?.channel ?? 'email',
            notes: options?.notes,
        });
        return response.data;
    },

    // Dunning Stage Config (Admin)
    getDunningStages: async () => {
        const response = await apiClient.get<DunningStagesListResponse>('/banking/settings/dunning-stages');
        return response.data;
    },

    createDunningStage: async (data: {
        stage_number: number;
        stage_name: string;
        trigger_days_after_due: number;
        action_type: string;
        template_id?: string;
        fee_amount?: number;
    }) => {
        const response = await apiClient.post<DunningStageConfig>('/banking/settings/dunning-stages', data);
        return response.data;
    },

    updateDunningStage: async (stageId: string, data: {
        stage_name?: string;
        trigger_days_after_due?: number;
        action_type?: string;
        template_id?: string;
        fee_amount?: number;
        is_active?: boolean;
    }) => {
        const response = await apiClient.put<DunningStageConfig>(`/banking/settings/dunning-stages/${stageId}`, data);
        return response.data;
    },

    reorderDunningStages: async (stageIds: string[]) => {
        const response = await apiClient.put<DunningStageConfig[]>('/banking/settings/dunning-stages/reorder', {
            stage_ids: stageIds,
        });
        return response.data;
    },

    // Customer Dunning Overrides
    getCustomerDunningSettings: async (businessEntityId: string) => {
        const response = await apiClient.get<CustomerDunningOverride>(`/banking/customers/${businessEntityId}/dunning-settings`);
        return response.data;
    },

    setCustomerDunningSettings: async (businessEntityId: string, data: {
        custom_payment_terms_days?: number;
        max_mahn_stufe?: number;
        preferred_contact_method?: string;
        exclude_from_auto_dunning?: boolean;
        exclusion_reason?: string;
        notes?: string;
    }) => {
        const response = await apiClient.put<CustomerDunningOverride>(`/banking/customers/${businessEntityId}/dunning-settings`, data);
        return response.data;
    },
};

// ==================== Zusaetzliche Types fuer erweitertes Mahnungswesen ====================

export interface MahnTask {
    id: string;
    dunning_record_id: string;
    task_type: MahnTaskType;
    assigned_user_id: string | null;
    due_date: string | null;
    status: MahnTaskStatus;
    priority: number;
    snoozed_until: string | null;
    snooze_count: number;
    snooze_reason: string | null;
    completed_at: string | null;
    completed_by_id: string | null;
    completion_notes: string | null;
    created_at: string;
    updated_at: string;
    invoice_number?: string;
    debtor_name?: string;
    outstanding_amount?: number;
    days_overdue?: number;
}

export interface MahnTaskSummary {
    pending_count: number;
    overdue_count: number;
    due_today_count: number;
    snoozed_count: number;
    by_type: Record<string, number>;
    by_priority: Record<number, number>;
}

export interface MahnungHistoryEntry {
    id: string;
    dunning_record_id: string;
    action_type: MahnungHistoryActionType;
    mahn_stufe: number;
    action_timestamp: string;
    performed_by_id: string | null;
    performed_by_name?: string;
    notes: string | null;
    outcome: string | null;
    document_id: string | null;
    metadata?: Record<string, unknown>;
}

export interface DunningRecord {
    id: string;
    document_id: string;
    invoice_number: string | null;
    invoice_date: string | null;
    due_date: string | null;
    gross_amount: number | null;
    outstanding_amount: number | null;
    currency: CurrencyCode;
    debtor_name: string | null;
    debtor_email: string | null;
    business_entity_id: string | null;
    dunning_level: DunningLevelNumber;
    status: string;
    reminder_fee: number;
    late_interest_rate: number | null;
    accrued_interest: number;
    total_outstanding: number | null;
    is_b2b: boolean;
    b2b_pauschale_claimed: boolean;
    mahnstopp: boolean;
    mahnstopp_reason: string | null;
    mahnstopp_until: string | null;
    first_reminder_at: string | null;
    second_reminder_at: string | null;
    final_reminder_at: string | null;
    next_action_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface PhoneCallLog {
    id: string;
    dunning_record_id: string;
    called_at: string;
    called_by_id: string | null;
    called_by_name?: string;
    contact_name: string;
    phone_number: string | null;
    outcome: PhoneCallOutcome;
    notes: string | null;
    follow_up_required: boolean;
    follow_up_date: string | null;
    follow_up_notes: string | null;
}

export interface PhoneCallLogCreate {
    contact_name: string;
    phone_number?: string;
    outcome: PhoneCallOutcome;
    notes?: string;
    follow_up_required?: boolean;
    follow_up_date?: string;
    follow_up_notes?: string;
}

export interface B2BPauschaleClaimResponse {
    dunning_id: string;
    pauschale_amount: number;
    already_claimed: boolean;
    success: boolean;
    message: string;
}

export interface VerzugszinsenCalculation {
    principal: number;
    due_date: string;
    as_of_date: string;
    is_b2b: boolean;
    interest_rate: number;
    days_overdue: number;
    interest_amount: number;
    total_with_interest: number;
    /** Basiszinssatz der Bundesbank */
    base_rate_percent?: number;
    /** Zusatzsatz (B2B: 9%, B2C: 5%) */
    zusatz_rate_percent?: number;
    /** Gesamtzinssatz */
    total_rate_percent?: number;
}

export interface BulkEscalateResponse {
    total: number;
    successful: number;
    failed: number;
    errors: Array<{ dunning_id: string; error: string }>;
}

export interface DunningStageConfig {
    id: string;
    user_id: string;
    stage_number: number;
    stage_name: string;
    trigger_days_after_due: number;
    action_type: DunningActionType;
    template_id: string | null;
    fee_amount: number;
    is_active: boolean;
    sort_order: number;
    created_at: string;
    updated_at: string;
}

export interface DunningStagesListResponse {
    stages: DunningStageConfig[];
    interest_rate_b2b: number;
    interest_rate_b2c: number;
    b2b_pauschale: number;
}

export interface CustomerDunningOverride {
    id: string;
    business_entity_id: string;
    business_entity_name?: string;
    custom_payment_terms_days: number | null;
    max_mahn_stufe: number | null;
    preferred_contact_method: string;
    exclude_from_auto_dunning: boolean;
    exclusion_reason: string | null;
    notes: string | null;
    created_at: string;
    updated_at: string;
}
