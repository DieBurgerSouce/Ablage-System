/**
 * TypeScript Types für Strukturierte Dokumenten-Extraktion.
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

/**
 * Quelle eines extrahierten Betrags für Audit-Trail.
 */
export type AmountSource = "document" | "computed" | "not_found";

/**
 * Status einer Validierungsprüfung.
 */
export type ValidationStatus = "valid" | "invalid" | "skipped" | "pending";

/**
 * Richtung einer Rechnung basierend auf Admin-Firmendaten.
 *
 * INCOMING: Eingangsrechnung - Empfänger ist die eigene Firma
 * OUTGOING: Ausgangsrechnung - Absender ist die eigene Firma
 * UNKNOWN: Keine eindeutige Zuordnung möglich
 */
export type InvoiceDirection = "incoming" | "outgoing" | "unknown";

// =============================================================================
// ADDRESS
// =============================================================================

export interface ExtractedAddress {
    company?: string;
    name?: string;
    person?: string;
    street?: string;
    street_number?: string;
    zip_code?: string;
    city?: string;
    country?: string;
}

// =============================================================================
// BANK ACCOUNT
// =============================================================================

export interface ExtractedBankAccount {
    iban?: string;
    bic?: string;
    bank_name?: string;
    account_holder?: string;
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
// VALIDATIONS
// =============================================================================

/**
 * Strukturierte Validierungsergebnisse für Audit und Qualitätssicherung.
 */
export interface ExtractionValidations {
    // IBAN-Validierung
    iban_checksum_valid?: boolean;
    iban_country_match?: boolean;

    // USt-IdNr-Validierung
    vat_country_match?: boolean;
    vies_vat_valid?: boolean;

    // Summen-Konsistenz
    sums_match?: boolean;
    sums_difference?: number;

    // Field-Level Confidence
    field_confidence?: Record<string, number>;
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
    supplier_number?: string;  // Lieferantennummer für ERP-Integration

    // Daten
    invoice_date?: string;
    invoice_date_raw?: string;  // Original-String aus Dokument (z.B. "06.04.2020")
    due_date?: string;
    due_date_raw?: string;      // Original-String aus Dokument
    service_period_start?: string;
    service_period_end?: string;

    // Absender
    sender?: ExtractedAddress;
    sender_vat_id?: string;
    sender_tax_number?: string;
    sender_bank?: ExtractedBankAccount;
    sender_email?: string;
    sender_phone?: string;
    sender_contact?: string;

    // Empfänger
    recipient?: ExtractedAddress;
    recipient_vat_id?: string;

    // Zusätzliche Lieferanteninformationen
    sender_tax_number_alternative?: string;

    // Lieferadresse (falls abweichend)
    delivery_address?: ExtractedAddress;

    // Lieferbedingungen
    delivery_terms?: string;

    // Steuerbefreiung bei innergemeinschaftlicher Lieferung
    reverse_charge_note?: string;
    is_reverse_charge?: boolean;
    vat_exemption_reason?: string;
    intra_community_supply?: boolean;

    // Betraege
    net_amount?: number;
    vat_rate?: number;
    vat_amount?: number;
    vat_amount_source?: AmountSource;  // Quelle: "document" | "computed" | "not_found"
    gross_amount?: number;
    gross_amount_source?: AmountSource;  // Quelle des Bruttobetrags
    currency?: string;
    vat_reason?: string;  // Grund für MwSt-Höhe (z.B. "intra-community supply / reverse charge")

    // Zahlungsbedingungen
    payment_terms?: string;
    payment_terms_days?: number;  // Zahlungsfrist in Tagen (strukturiert)
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

    // OCR Metadaten
    page_count?: number;
    ocr_confidence_score?: number;

    // Validierungsergebnisse
    validations?: ExtractionValidations;

    // Eingangs-/Ausgangsrechnung-Erkennung
    invoice_direction?: InvoiceDirection;
    invoice_direction_confidence?: number;
    invoice_direction_reason?: string;
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
    // HINWEIS: needs_review und extraction_warnings sind auf den typspezifischen
    // Daten (invoice, order, contract), nicht auf Top-Level

    // Meta
    document_hash?: string;  // SHA256 Hash des Originaldokuments (sha256:...)
    extraction_version?: string;  // Version des Extraktionsalgorithmus
    extracted_at?: string;  // ISO 8601 Zeitstempel

    // Übersetzungs-Metadaten
    original_language?: string;  // ISO 639-1
    was_translated?: boolean;
    translation_confidence?: number;
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
