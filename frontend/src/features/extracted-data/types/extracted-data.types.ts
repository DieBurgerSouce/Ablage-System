/**
 * TypeScript Types fuer Strukturierte Dokumenten-Extraktion.
 *
 * Spiegelt die Pydantic-Modelle aus dem Backend wider.
 */

// =============================================================================
// ENUMS
// =============================================================================

export type ExtractedDocumentType =
    | "invoice"
    | "order"
    | "contract"
    | "delivery_note"
    | "receipt"
    | "unknown";

// =============================================================================
// ADDRESS
// =============================================================================

export interface ExtractedAddress {
    company?: string;
    name?: string;
    street?: string;
    zip_code?: string;
    city?: string;
    country?: string;
}

// =============================================================================
// LINE ITEMS
// =============================================================================

export interface ExtractedLineItem {
    position: number;
    article_number?: string;
    description?: string;
    quantity?: number;
    unit?: string;
    unit_price?: number;
    total_price?: number;
    vat_rate?: number;
}

// =============================================================================
// INVOICE DATA
// =============================================================================

export interface ExtractedInvoiceData {
    document_type: "invoice";

    // Identifikation
    invoice_number?: string;
    order_number?: string;
    customer_number?: string;
    delivery_note_number?: string;

    // Daten
    invoice_date?: string;
    due_date?: string;
    service_period_start?: string;
    service_period_end?: string;

    // Absender
    sender?: ExtractedAddress;
    sender_vat_id?: string;
    sender_tax_number?: string;
    sender_bank?: {
        iban?: string;
        bic?: string;
        bank_name?: string;
    };
    sender_email?: string;
    sender_phone?: string;

    // Empfaenger
    recipient?: ExtractedAddress;
    recipient_vat_id?: string;

    // Betraege
    net_amount?: number;
    vat_rate?: number;
    vat_amount?: number;
    gross_amount?: number;
    currency?: string;

    // Zahlungsbedingungen
    payment_terms?: string;
    payment_method?: string;
    discount_percent?: number;
    discount_days?: number;
    discount_amount?: number;
    discount_due_date?: string;
    early_payment_info?: string;
    late_payment_info?: string;

    // Positionen
    line_items?: ExtractedLineItem[];

    // Meta
    extraction_confidence?: number;
    needs_review?: boolean;
    extraction_warnings?: string[];
}

// =============================================================================
// ORDER DATA
// =============================================================================

export interface ExtractedOrderData {
    document_type: "order";

    // Identifikation
    order_number?: string;
    customer_order_number?: string;
    quotation_number?: string;

    // Daten
    order_date?: string;
    delivery_date?: string;
    confirmation_date?: string;
    validity_date?: string;

    // Besteller
    orderer?: ExtractedAddress;
    orderer_contact?: string;

    // Lieferant
    supplier?: ExtractedAddress;
    supplier_contact?: string;

    // Lieferadresse
    delivery_address?: ExtractedAddress;

    // Positionen
    line_items?: ExtractedLineItem[];

    // Betraege
    total_amount?: number;
    currency?: string;

    // Bedingungen
    payment_terms?: string;
    delivery_terms?: string;
    incoterms?: string;

    // Meta
    extraction_confidence?: number;
    needs_review?: boolean;
    extraction_warnings?: string[];
}

// =============================================================================
// CONTRACT DATA
// =============================================================================

export interface ExtractedContractData {
    document_type: "contract";

    // Identifikation
    contract_number?: string;
    contract_type?: string;
    previous_contract?: string;

    // Laufzeit
    contract_date?: string;
    start_date?: string;
    end_date?: string;
    duration_months?: number;
    notice_period?: string;
    notice_deadline?: string;
    auto_renewal?: boolean;
    renewal_period?: string;

    // Vertragspartner
    party_a?: ExtractedAddress;
    party_a_signatory?: string;
    party_b?: ExtractedAddress;
    party_b_signatory?: string;

    // Werte
    contract_value?: number;
    monthly_value?: number;
    currency?: string;

    // Inhalt
    subject?: string;

    // Meta
    extraction_confidence?: number;
    needs_review?: boolean;
    extraction_warnings?: string[];
}

// =============================================================================
// CLASSIFICATION
// =============================================================================

export interface DocumentClassification {
    document_type: ExtractedDocumentType;
    confidence: number;
    matched_keywords?: string[];
}

// =============================================================================
// FULL EXTRACTION RESULT
// =============================================================================

export interface ExtractedDocumentData {
    classification: DocumentClassification;
    invoice?: ExtractedInvoiceData;
    order?: ExtractedOrderData;
    contract?: ExtractedContractData;

    // Allgemeine Entities
    ibans?: string[];
    vat_ids?: string[];
    companies?: string[];
    dates?: string[];
    amounts?: number[];

    // Gesamt-Konfidenz
    overall_confidence?: number;
    needs_review?: boolean;
    extraction_warnings?: string[];
}

// =============================================================================
// SEARCH & LIST TYPES
// =============================================================================

export interface ExtractedDataSearchResult {
    document_id: string;
    document_type: ExtractedDocumentType;
    confidence: number;
    reference_number?: string;
    document_date?: string;
    gross_amount?: number;
    matched_field?: string;
    matched_value?: string;
    preview_text?: string;
    filename?: string;
}

export interface PaginatedSearchResponse {
    items: ExtractedDataSearchResult[];
    total: number;
    page: number;
    per_page: number;
    pages: number;
}

export interface InvoiceSummary {
    document_id: string;
    invoice_number?: string;
    invoice_date?: string;
    due_date?: string;
    sender_company?: string;
    gross_amount?: number;
    currency: string;
    has_skonto: boolean;
    discount_percent?: number;
    discount_due_date?: string;
    extraction_confidence: number;
    needs_review: boolean;
    filename?: string;
}

export interface PaginatedInvoiceList {
    items: InvoiceSummary[];
    total: number;
    page: number;
    per_page: number;
    pages: number;
}

export interface MonthlyAggregation {
    month: string;
    count: number;
    gross_amount: number;
    net_amount: number;
}

export interface ExtractedDataAggregations {
    total_documents: number;
    total_gross_amount: number;
    total_net_amount: number;
    total_vat_amount: number;
    avg_gross_amount: number;
    by_month: MonthlyAggregation[];
    by_document_type: Record<string, number>;
}

// =============================================================================
// SEARCH PARAMS
// =============================================================================

export interface ExtractedDataSearchParams {
    invoice_number?: string;
    customer_number?: string;
    iban?: string;
    vat_id?: string;
    min_amount?: number;
    max_amount?: number;
    date_from?: string;
    date_to?: string;
    document_type?: ExtractedDocumentType;
    needs_review?: boolean;
    has_skonto?: boolean;
    page?: number;
    per_page?: number;
}

export interface InvoiceListParams {
    overdue?: boolean;
    has_skonto?: boolean;
    skonto_expiring_soon?: boolean;
    min_amount?: number;
    max_amount?: number;
    order_by?: "invoice_date" | "gross_amount" | "due_date";
    order_dir?: "asc" | "desc";
    page?: number;
    per_page?: number;
}
