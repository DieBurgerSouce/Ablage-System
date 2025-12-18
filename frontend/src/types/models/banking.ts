/**
 * Banking Model Types
 *
 * Typen fuer Banking-Funktionen: Konten, Transaktionen, Zahlungen,
 * Mahnwesen, Cash-Flow und Skonto.
 */

import type { TimestampedEntity, PaginatedResponse } from '../api/common';

// ==================== Common Banking Types ====================

/**
 * Currency code (ISO 4217)
 */
export type CurrencyCode = 'EUR' | 'USD' | 'CHF' | 'GBP';

/**
 * Cash flow scenario type
 */
export type CashFlowScenarioType = 'optimistic' | 'realistic' | 'pessimistic';

// ==================== Bank Account ====================

/**
 * Bank account type
 */
export type BankAccountType = 'checking' | 'savings' | 'business' | 'credit';

/**
 * Bank account connection status
 */
export type ConnectionStatus = 'connected' | 'disconnected' | 'error' | 'pending';

/**
 * Bank account entity
 */
export interface BankAccount {
    id: string;
    user_id: string;
    account_name: string;
    iban: string;
    bic: string | null;
    bank_name: string | null;
    account_holder: string | null;
    account_type: BankAccountType;
    currency: CurrencyCode;
    is_active: boolean;
    connection_status: ConnectionStatus;
    current_balance: number | null;
    balance_date: string | null;
    last_sync_at: string | null;
    auto_sync_enabled: boolean;
    created_at: string;
    updated_at: string;
}

/**
 * Bank account with statistics
 */
export interface BankAccountWithStats {
    id: string;
    name: string;
    iban: string;
    bank_name: string | null;
    currency: CurrencyCode;
    is_active: boolean;
    transaction_count: number;
    last_import_date: string | null;
    balance: number | null;
    unmatched_count: number;
}

/**
 * Bank account create request
 */
export interface BankAccountCreate {
    account_name: string;
    iban: string;
    bic?: string;
    bank_name?: string;
    account_holder?: string;
    account_type?: BankAccountType;
    currency?: CurrencyCode;
}

/**
 * Bank account update request
 */
export interface BankAccountUpdate {
    account_name?: string;
    bank_name?: string;
    account_holder?: string;
    account_type?: BankAccountType;
    is_active?: boolean;
    auto_sync_enabled?: boolean;
}

// ==================== Transactions ====================

/**
 * Transaction type
 */
export type TransactionType = 'transfer' | 'direct_debit' | 'card' | 'cash' | 'fee' | 'interest' | 'other';

/**
 * Reconciliation status
 */
export type ReconciliationStatus = 'unmatched' | 'matched' | 'partial' | 'manual' | 'ignored';

/**
 * Bank transaction entity
 */
export interface BankTransaction {
    id: string;
    bank_account_id: string;
    transaction_id: string | null;
    booking_date: string;
    value_date: string;
    amount: number;
    currency: CurrencyCode;
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

/**
 * Transaction filter parameters
 */
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

/**
 * Transaction list response
 */
export type TransactionListResponse = PaginatedResponse<BankTransaction>;

/**
 * Transaction update request
 */
export interface TransactionUpdate {
    notes?: string;
    tags?: string[];
    category?: string;
}

/**
 * Transaction statistics
 */
export interface TransactionStats {
    total_count: number;
    total_inflow: number;
    total_outflow: number;
    matched_count: number;
    unmatched_count: number;
    match_rate: number;
    avg_transaction_amount: number;
}

// ==================== Import ====================

/**
 * Supported import format
 */
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

/**
 * Import preview
 */
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

/**
 * Import response
 */
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

/**
 * Supported format info
 */
export interface SupportedFormat {
    format: ImportFormat;
    name: string;
    description: string;
    extensions: string[];
}

// ==================== Reconciliation ====================

/**
 * Match candidate for reconciliation
 */
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

/**
 * Reconciliation result
 */
export interface ReconciliationResult {
    transaction_id: string;
    status: ReconciliationStatus;
    matched_document_id: string | null;
    match_confidence: number | null;
    match_method: string | null;
}

/**
 * Batch reconciliation result
 */
export interface BatchReconciliationResult {
    total_processed: number;
    matched_count: number;
    partial_count: number;
    unmatched_count: number;
    match_rate: number;
    results: ReconciliationResult[];
}

/**
 * Split item for partial payments
 */
export interface SplitItem {
    document_id: string;
    amount: number;
}

// ==================== Payments ====================

/**
 * Payment status
 */
export type PaymentStatus =
    | 'draft'
    | 'pending_approval'
    | 'approved'
    | 'pending_tan'
    | 'submitted'
    | 'executed'
    | 'failed'
    | 'cancelled';

/**
 * Payment type
 */
export type PaymentType = 'transfer' | 'direct_debit' | 'batch';

/**
 * SEPA type
 */
export type SEPAType = 'pain_001' | 'pain_008';

/**
 * Payment order entity
 */
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
    currency: CurrencyCode;
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

/**
 * Payment order create request
 */
export interface PaymentOrderCreate {
    bank_account_id: string;
    document_id?: string;
    beneficiary_name: string;
    beneficiary_iban: string;
    beneficiary_bic?: string;
    amount: number;
    currency?: CurrencyCode;
    reference?: string;
    execution_date?: string;
    use_skonto?: boolean;
}

/**
 * Payment list response
 */
export interface PaymentListResponse {
    payments: PaymentOrder[];
    total: number;
    offset: number;
    limit: number;
}

/**
 * TAN challenge
 */
export interface TANChallenge {
    session_id: string;
    challenge_text: string;
    tan_method: string;
    expires_at: string;
}

/**
 * TAN method type
 */
export type TANMethodType = 'pushTAN' | 'photoTAN' | 'chipTAN' | 'smsTAN' | 'appTAN';

/**
 * TAN method
 */
export interface TANMethod {
    id: string;
    name: string;
    type: TANMethodType;
    description: string;
}

// ==================== Skonto ====================

/**
 * Skonto opportunity
 */
export interface SkontoOpportunity {
    document_id: string;
    invoice_number: string | null;
    invoice_date: string | null;
    due_date: string | null;
    days_until_due: number;
    gross_amount: number;
    currency: CurrencyCode;
    beneficiary_name: string | null;
    beneficiary_iban: string | null;
    has_skonto: boolean;
    skonto_percent: number | null;
    skonto_deadline: string | null;
    skonto_amount: number | null;
    amount_with_skonto: number | null;
    skonto_days_remaining: number | null;
}

// ==================== Cash Flow ====================

/**
 * Cash flow forecast
 */
export interface CashFlowForecast {
    period: {
        start: string;
        end: string;
        scenario: CashFlowScenarioType;
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

/**
 * Cash flow summary
 */
export interface CashFlowSummary {
    current_balance: number;
    short_term: CashFlowPeriod;
    medium_term: CashFlowPeriod;
    long_term: CashFlowPeriod;
    warnings: string[];
}

/**
 * Cash flow period data
 */
export interface CashFlowPeriod {
    days: number;
    inflow: number;
    outflow: number;
    net: number;
    ending_balance: number;
}

/**
 * Daily cash flow entry
 */
export interface DailyCashFlowEntry {
    date: string;
    inflow: number;
    outflow: number;
    net: number;
    cumulative: number;
}

/**
 * Cash flow scenario
 */
export interface CashFlowScenario {
    scenario: string;
    total_inflow: number;
    total_outflow: number;
    net_flow: number;
    min_balance: number;
    days_negative: number;
}

/**
 * Scenario comparison
 */
export interface ScenarioComparison {
    optimistic: CashFlowScenario;
    realistic: CashFlowScenario;
    pessimistic: CashFlowScenario;
}

// ==================== Dunning (Mahnwesen) ====================

/**
 * Dunning level
 */
export type DunningLevel = 'first_reminder' | 'second_reminder' | 'final_reminder';

/**
 * Dunning statistics
 */
export interface DunningStats {
    total_active: number;
    by_level: Record<DunningLevel, number>;
    total_amount_overdue: number;
    total_fees: number;
    total_interest: number;
    avg_days_overdue: number;
    success_rate_30d: number;
}

/**
 * Overdue invoice
 */
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

// ==================== Aging Report ====================

/**
 * Aging bucket
 */
export interface AgingBucket {
    bucket: string;
    count: number;
    amount: number;
    percentage: number;
}

/**
 * Aging line item
 */
export interface AgingLineItem {
    document_id: string;
    invoice_number: string;
    counterparty: string;
    due_date: string | null;
    amount: number;
    bucket: string;
    days_overdue: number;
}

/**
 * Aging report type
 */
export type AgingReportType = 'receivables' | 'payables';

/**
 * Aging report
 */
export interface AgingReport {
    report_type: AgingReportType;
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

/**
 * Aging summary
 */
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

/**
 * Top debtor/creditor
 */
export interface TopDebtor {
    counterparty: string;
    total_amount: number;
    invoice_count: number;
    oldest_due_date: string | null;
    avg_days_overdue: number;
}

/**
 * Days Sales Outstanding (DSO)
 */
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
