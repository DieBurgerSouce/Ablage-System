/**
 * Intercompany Reconciliation API Client
 *
 * API-Funktionen für IC-Abstimmung und Konsolidierung.
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface ICTransaction {
    id: string;
    from_company_id: string;
    from_company_name: string;
    to_company_id: string;
    to_company_name: string;
    transaction_type: ICTransactionType;
    amount: number;
    currency: string;
    reference: string;
    document_id?: string;
    invoice_id?: string;
    transaction_date: string;
    due_date?: string;
    description?: string;
    status: ICTransactionStatus;
    matched_transaction_id?: string;
}

export type ICTransactionType =
    | 'receivable'
    | 'payable'
    | 'loan'
    | 'service_fee'
    | 'dividend'
    | 'capital_contribution'
    | 'cost_allocation';

export type ICTransactionStatus =
    | 'open'
    | 'matched'
    | 'partial_match'
    | 'disputed'
    | 'closed';

export interface ICBalance {
    company_a_id: string;
    company_a_name: string;
    company_b_id: string;
    company_b_name: string;
    balance_a_to_b: number;
    balance_b_to_a: number;
    net_balance: number;
    open_transactions_count: number;
    last_reconciled_at?: string;
    currency: string;
}

export interface ReconciliationDifference {
    id: string;
    difference_type: DifferenceType;
    from_company_id: string;
    to_company_id: string;
    transaction_id?: string;
    counterpart_id?: string;
    expected_amount: number;
    actual_amount: number;
    difference_amount: number;
    expected_date?: string;
    actual_date?: string;
    description: string;
    recommendation: string;
    created_at: string;
}

export type DifferenceType =
    | 'unmatched'
    | 'amount_mismatch'
    | 'date_mismatch'
    | 'duplicate'
    | 'partial_match';

export interface EliminationEntry {
    id: string;
    account_debit: string;
    account_credit: string;
    amount: number;
    description: string;
    from_company_id: string;
    to_company_id: string;
    transaction_ids: string[];
    elimination_type: string;
    period: string;
}

export interface ICSummary {
    has_ic_relationships: boolean;
    company_pairs: number;
    total_ic_receivables: number;
    total_ic_payables: number;
    net_ic_position: number;
    open_transactions: number;
    currency: string;
    generated_at: string;
    message?: string;
}

export interface ICTransactionsListResponse {
    total: number;
    period_start: string;
    period_end: string;
    transactions: ICTransaction[];
}

export interface ICBalancesResponse {
    as_of_date: string;
    balances: ICBalance[];
}

export interface ReconciliationResult {
    total_transactions: number;
    matched: number;
    unmatched: number;
    match_rate: number;
    differences: ReconciliationDifference[];
    transactions: ICTransaction[];
}

export interface EliminationsResponse {
    period: string;
    eliminations: EliminationEntry[];
    total_eliminated: number;
}

export interface ReconciliationReport {
    generated_at: string;
    period_start: string;
    period_end: string;
    companies_involved: Array<{ id: string; name: string }>;
    total_ic_volume: number;
    matched_volume: number;
    unmatched_volume: number;
    balances: ICBalance[];
    differences: ReconciliationDifference[];
    eliminations: EliminationEntry[];
    statistics: {
        match_rate: number;
        total_transactions: number;
        matched_count: number;
        unmatched_count: number;
        total_differences: number;
    };
}

// ==================== API Functions ====================

/**
 * Hole IC-Zusammenfassung
 */
export async function getICSummary(companyIds?: string[]): Promise<ICSummary> {
    const params = new URLSearchParams();
    if (companyIds?.length) {
        companyIds.forEach((id) => params.append('company_ids', id));
    }
    const query = params.toString();
    const url = query ? `/holding/ic/summary?${query}` : '/holding/ic/summary';
    const response = await apiClient.get<ICSummary>(url);
    return response.data;
}

/**
 * Hole IC-Transaktionen
 */
export async function getICTransactions(params: {
    companyIds?: string[];
    startDate?: string;
    endDate?: string;
    transactionType?: ICTransactionType;
}): Promise<ICTransactionsListResponse> {
    const searchParams = new URLSearchParams();
    if (params.companyIds?.length) {
        params.companyIds.forEach((id) => searchParams.append('company_ids', id));
    }
    if (params.startDate) {
        searchParams.append('start_date', params.startDate);
    }
    if (params.endDate) {
        searchParams.append('end_date', params.endDate);
    }
    if (params.transactionType) {
        searchParams.append('transaction_type', params.transactionType);
    }
    const query = searchParams.toString();
    const url = query
        ? `/holding/ic/transactions?${query}`
        : '/holding/ic/transactions';
    const response = await apiClient.get<ICTransactionsListResponse>(url);
    return response.data;
}

/**
 * Hole IC-Salden zwischen Firmen
 */
export async function getICBalances(companyIds?: string[]): Promise<ICBalancesResponse> {
    const params = new URLSearchParams();
    if (companyIds?.length) {
        companyIds.forEach((id) => params.append('company_ids', id));
    }
    const query = params.toString();
    const url = query ? `/holding/ic/balances?${query}` : '/holding/ic/balances';
    const response = await apiClient.get<ICBalancesResponse>(url);
    return response.data;
}

/**
 * Führe IC-Abstimmung durch
 */
export async function performReconciliation(params: {
    companyIds?: string[];
    startDate?: string;
    endDate?: string;
}): Promise<ReconciliationResult> {
    const searchParams = new URLSearchParams();
    if (params.companyIds?.length) {
        params.companyIds.forEach((id) => searchParams.append('company_ids', id));
    }
    if (params.startDate) {
        searchParams.append('start_date', params.startDate);
    }
    if (params.endDate) {
        searchParams.append('end_date', params.endDate);
    }
    const query = searchParams.toString();
    const url = query ? `/holding/ic/reconcile?${query}` : '/holding/ic/reconcile';
    const response = await apiClient.post<ReconciliationResult>(url, {});
    return response.data;
}

/**
 * Generiere Eliminierungsbuchungen
 */
export async function getEliminations(params: {
    companyIds?: string[];
    period?: string;
}): Promise<EliminationsResponse> {
    const searchParams = new URLSearchParams();
    if (params.companyIds?.length) {
        params.companyIds.forEach((id) => searchParams.append('company_ids', id));
    }
    if (params.period) {
        searchParams.append('period', params.period);
    }
    const query = searchParams.toString();
    const url = query
        ? `/holding/ic/eliminations?${query}`
        : '/holding/ic/eliminations';
    const response = await apiClient.get<EliminationsResponse>(url);
    return response.data;
}

/**
 * Generiere vollständigen Abstimmungsbericht
 */
export async function getReconciliationReport(params: {
    companyIds?: string[];
    startDate?: string;
    endDate?: string;
}): Promise<ReconciliationReport> {
    const searchParams = new URLSearchParams();
    if (params.companyIds?.length) {
        params.companyIds.forEach((id) => searchParams.append('company_ids', id));
    }
    if (params.startDate) {
        searchParams.append('start_date', params.startDate);
    }
    if (params.endDate) {
        searchParams.append('end_date', params.endDate);
    }
    const query = searchParams.toString();
    const url = query ? `/holding/ic/report?${query}` : '/holding/ic/report';
    const response = await apiClient.get<ReconciliationReport>(url);
    return response.data;
}
