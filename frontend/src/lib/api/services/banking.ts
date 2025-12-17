import { apiClient } from '../client';

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
    by_level: {
        first_reminder: number;
        second_reminder: number;
        final_reminder: number;
    };
    total_amount_overdue: number;
    total_fees: number;
    total_interest: number;
    avg_days_overdue: number;
    success_rate_30d: number;
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
        const response = await apiClient.post<{
            total_processed: number;
            matched_count: number;
            partial_count: number;
            unmatched_count: number;
            match_rate: number;
        }>('/banking/reconciliation/batch', null, { params });
        return response.data;
    },
};
