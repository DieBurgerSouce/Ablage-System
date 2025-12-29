/**
 * Banking Model Types
 *
 * Typen für Banking-Funktionen: Konten, Transaktionen, Zahlungen,
 * Mahnwesen, Cash-Flow und Skonto.
 */

import type { PaginatedResponse } from '../api/common';

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
 * Vorschau einer zu importierenden Transaktion
 */
export interface ImportTransactionPreview {
    booking_date: string;
    value_date?: string;
    amount: number;
    currency?: CurrencyCode;
    counterparty_name?: string;
    counterparty_iban?: string;
    reference_text?: string;
    booking_text?: string;
}

/**
 * Import-Fehler mit Details
 */
export interface ImportError {
    row?: number;
    field?: string;
    message: string;
    raw_data?: string;
}

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
    sample_transactions: ImportTransactionPreview[];
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
    errors: ImportError[];
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
 * Details zum Abgleich (Matching)
 */
export interface MatchDetails {
    amount_match?: boolean;
    amount_difference?: number;
    name_similarity?: number;
    iban_match?: boolean;
    reference_match?: boolean;
    date_proximity_days?: number;
    rules_applied?: string[];
}

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
    match_details: MatchDetails;
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
 * Numerischer Mahnstufen-Level (entspricht Datenbank-Werten)
 * 0 = Neu, 1 = Erinnerung, 2 = 1. Mahnung, 3 = 2. Mahnung, 4 = Letzte Mahnung, 5 = Inkasso
 */
export type DunningLevelNumber = 0 | 1 | 2 | 3 | 4 | 5;

/**
 * String-basierter Dunning Level (für Legacy-Kompatibilität)
 * @deprecated Nutze DunningLevelNumber für neue Implementierungen
 */
export type DunningLevel = 'first_reminder' | 'second_reminder' | 'final_reminder';

/**
 * Mapping von Mahnstufe zu Anzeigenamen (Deutsch)
 */
export const DUNNING_LEVEL_NAMES: Record<DunningLevelNumber, string> = {
    0: 'Neu',
    1: 'Erinnerung',
    2: '1. Mahnung',
    3: '2. Mahnung',
    4: 'Letzte Mahnung',
    5: 'Inkasso',
};

/**
 * Dunning statistics
 */
export interface DunningStats {
    total_active: number;
    by_level: Record<DunningLevelNumber, number>;
    total_amount_overdue: number;
    total_fees: number;
    total_interest: number;
    avg_days_overdue: number;
    success_rate_30d: number;
    /** Anzahl Mahnvorgänge mit aktivem Mahnstopp */
    mahnstopp_count?: number;
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

// ==================== Erweitertes Mahnungswesen (BGB §286) ====================

/**
 * Mahnaufgaben-Typ
 */
export type MahnTaskType = 'reminder' | 'escalate' | 'phone_call' | 'review' | 'collection';

/**
 * Mahnaufgaben-Status
 */
export type MahnTaskStatus = 'pending' | 'in_progress' | 'completed' | 'snoozed' | 'cancelled';

/**
 * Telefonkontakt-Ergebnis
 */
export type PhoneCallOutcome =
    | 'reached'
    | 'not_reached'
    | 'voicemail'
    | 'callback_requested'
    | 'payment_promised'
    | 'dispute_raised';

/**
 * Aktionstyp für Mahnstufen
 */
export type DunningActionType = 'email' | 'letter' | 'phone' | 'escalation';

/**
 * History-Aktionstyp
 */
export type MahnungHistoryActionType =
    | 'reminder_sent'
    | 'escalated'
    | 'phone_call'
    | 'payment_received'
    | 'partial_payment'
    | 'mahnstopp_set'
    | 'mahnstopp_lifted'
    | 'b2b_pauschale_claimed'
    | 'task_created'
    | 'task_completed'
    | 'note_added'
    | 'status_changed';

/**
 * Bevorzugte Kontaktmethode
 */
export type ContactMethod = 'email' | 'phone' | 'letter';

/**
 * Erweiterter Mahnvorgang mit BGB §286 Feldern
 */
export interface DunningRecord {
    id: string;
    document_id: string;
    invoice_number: string | null;
    invoice_date: string | null;
    due_date: string | null;
    gross_amount: number | null;
    outstanding_amount: number | null;
    currency: CurrencyCode;

    // Schuldner
    debtor_name: string | null;
    debtor_email: string | null;
    business_entity_id: string | null;

    // Mahnung
    dunning_level: DunningLevelNumber;
    status: string;

    // Gebuehren
    reminder_fee: number;
    late_interest_rate: number | null;
    accrued_interest: number;
    total_outstanding: number | null;

    // BGB §286 - B2B/B2C Unterscheidung
    is_b2b: boolean;
    b2b_pauschale_claimed: boolean;

    // Mahnstopp (bei Reklamation)
    mahnstopp: boolean;
    mahnstopp_reason: string | null;
    mahnstopp_until: string | null;

    // Timeline
    first_reminder_at: string | null;
    second_reminder_at: string | null;
    final_reminder_at: string | null;
    next_action_at: string | null;

    created_at: string;
    updated_at: string;
}

/**
 * Mahnaufgabe
 */
export interface MahnTask {
    id: string;
    dunning_record_id: string;
    task_type: MahnTaskType;
    assigned_user_id: string | null;
    due_date: string | null;
    status: MahnTaskStatus;
    priority: number;

    // Snooze (max 3x)
    snoozed_until: string | null;
    snooze_count: number;
    snooze_reason: string | null;

    // Completion
    completed_at: string | null;
    completed_by_id: string | null;
    completion_notes: string | null;

    created_at: string;
    updated_at: string;

    // Erweiterte Infos (optional)
    invoice_number?: string;
    debtor_name?: string;
    outstanding_amount?: number;
    days_overdue?: number;
    /** Aufgabenbeschreibung (UI-Anzeige) */
    description?: string;
}

/**
 * Mahnaufgabe mit vollstaendigen Dunning-Details
 */
export interface MahnTaskWithDunning extends MahnTask {
    dunning_record?: DunningRecord;
}

/**
 * Filter für Mahnaufgaben
 */
export interface MahnTaskFilter {
    task_type?: MahnTaskType;
    status?: MahnTaskStatus;
    assigned_user_id?: string;
    due_date_from?: string;
    due_date_to?: string;
    priority?: number;
    include_snoozed?: boolean;
}

/**
 * Anfrage zum Zurückstellen einer Aufgabe
 */
export interface MahnTaskSnoozeRequest {
    snooze_until: string;
    reason?: string;
}

/**
 * Anfrage zum Abschließen einer Aufgabe
 */
export interface MahnTaskCompleteRequest {
    notes?: string;
}

/**
 * Zusammenfassung der Mahnaufgaben
 */
export interface MahnTaskSummary {
    pending_count: number;
    overdue_count: number;
    due_today_count: number;
    snoozed_count: number;
    by_type: Record<string, number>;
    by_priority: Record<number, number>;
}

/**
 * Telefonprotokoll
 */
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

/**
 * Anfrage zum Erstellen eines Telefonprotokolls
 */
export interface PhoneCallLogCreate {
    contact_name: string;
    phone_number?: string;
    outcome: PhoneCallOutcome;
    notes?: string;
    follow_up_required?: boolean;
    follow_up_date?: string;
    follow_up_notes?: string;
}

/**
 * Mahnstufen-Konfiguration
 */
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
    // Erweiterte Felder für UI
    /** @deprecated Nutze stage_number */
    stage_level?: number;
    /** Alias für trigger_days_after_due */
    days_after_previous?: number;
    /** Kommunikationskanal (email, letter, phone, none) */
    communication_channel?: 'email' | 'letter' | 'phone' | 'none';
    /** Automatische Eskalation aktiviert */
    auto_escalate?: boolean;
    /** Freigabe erforderlich vor Eskalation */
    requires_approval?: boolean;
}

/**
 * Anfrage zum Erstellen einer Mahnstufe
 */
export interface DunningStageConfigCreate {
    stage_number: number;
    stage_name: string;
    trigger_days_after_due: number;
    action_type: DunningActionType;
    template_id?: string;
    fee_amount?: number;
}

/**
 * Anfrage zum Aktualisieren einer Mahnstufe
 */
export interface DunningStageConfigUpdate {
    stage_name?: string;
    trigger_days_after_due?: number;
    action_type?: DunningActionType;
    template_id?: string;
    fee_amount?: number;
    is_active?: boolean;
}

/**
 * Liste der Mahnstufen mit Zinssaetzen
 */
export interface DunningStagesListResponse {
    stages: DunningStageConfig[];
    interest_rate_b2b: number;
    interest_rate_b2c: number;
    b2b_pauschale: number;
}

/**
 * Kundenspezifische Mahneinstellungen
 */
export interface CustomerDunningOverride {
    id: string;
    business_entity_id: string;
    business_entity_name?: string;
    custom_payment_terms_days: number | null;
    max_mahn_stufe: number | null;
    preferred_contact_method: ContactMethod;
    exclude_from_auto_dunning: boolean;
    exclusion_reason: string | null;
    notes: string | null;
    created_at: string;
    updated_at: string;
}

/**
 * Anfrage zum Setzen kundenspezifischer Mahneinstellungen
 */
export interface CustomerDunningOverrideUpdate {
    custom_payment_terms_days?: number;
    max_mahn_stufe?: number;
    preferred_contact_method?: ContactMethod;
    exclude_from_auto_dunning?: boolean;
    exclusion_reason?: string;
    notes?: string;
}

/**
 * Metadata für History-Einträge
 */
export interface MahnungHistoryMetadata {
    /** Vorheriger Wert (z.B. bei Status-Änderung) */
    previous_value?: string | number;
    /** Neuer Wert */
    new_value?: string | number;
    /** Kanal der Kommunikation */
    channel?: 'email' | 'letter' | 'phone';
    /** Betrag bei Zahlung */
    payment_amount?: number;
    /** Mahnstopp-Grund */
    mahnstopp_reason?: string;
    /** Mahnstopp-Bis-Datum */
    mahnstopp_until?: string;
    /** Telefon-Ergebnis */
    call_outcome?: PhoneCallOutcome;
    /** Zusätzliche Hinweise */
    additional_info?: string;
}

/**
 * Mahnung-History-Eintrag (Audit-Log)
 */
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
    metadata?: MahnungHistoryMetadata;
}

/**
 * Alias für MahnungHistoryEntry (Kompatibilitaet)
 */
export type MahnungHistory = MahnungHistoryEntry;

/**
 * Anfrage zum Setzen eines Mahnstopps
 */
export interface MahnstoppSetRequest {
    reason: string;
    until_date?: string;
}

/**
 * Anfrage zur Masseneskalation
 */
export interface BulkEscalateRequest {
    dunning_ids: string[];
    notes?: string;
}

/**
 * Ergebnis der Masseneskalation
 */
export interface BulkEscalateResponse {
    total: number;
    successful: number;
    failed: number;
    errors: Array<{ dunning_id: string; error: string }>;
}

/**
 * B2B-Pauschale Claim Response
 */
export interface B2BPauschaleClaimResponse {
    dunning_id: string;
    pauschale_amount: number;
    already_claimed: boolean;
    success: boolean;
    message: string;
}

/**
 * Verzugszinsen-Berechnung
 */
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

/**
 * Ergebnis des taeglichen Mahnlaufs
 */
export interface MahnlaufResult {
    run_date: string;
    is_business_day: boolean;
    skipped_reason: string | null;
    candidates_found: number;
    tasks_created: number;
    skipped_mahnstopp: number;
    skipped_excluded: number;
    errors: Array<{ dunning_id: string; error: string }>;
    duration_seconds: number;
}

/**
 * Kanban-Spalten-Status für Mahnwesen
 */
export type MahnKanbanColumn = 'pending' | 'reminder_sent' | 'escalated' | 'completed';

/**
 * Kanban-Karte für Mahnwesen
 */
export interface MahnKanbanCard {
    id: string;
    dunning_id: string;
    invoice_number: string;
    debtor_name: string;
    outstanding_amount: number;
    days_overdue: number;
    dunning_level: number;
    status: MahnKanbanColumn;
    has_mahnstopp: boolean;
    is_b2b: boolean;
    priority: number;
}
