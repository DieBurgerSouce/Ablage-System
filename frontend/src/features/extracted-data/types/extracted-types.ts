/**
 * Types for extracted document data (OCR Review)
 * Supports Invoice, Order, and Contract document types
 */

// Base confidence level for extracted fields
export type ConfidenceLevel = 'high' | 'medium' | 'low';

// Document types supported
export type DocumentType = 'invoice' | 'order' | 'contract' | 'other';

// Base extracted field structure
export interface ExtractedField {
  value: string;
  german_label: string;
  confidence: number;
  source?: string;
  position?: number;
  validated?: boolean;
  edited?: boolean;
  original_value?: string;
}

// Invoice-specific fields (from german_validator.py INVOICE_FIELDS)
export interface InvoiceData {
  invoice_number?: ExtractedField;
  invoice_date?: ExtractedField;
  service_period?: ExtractedField;
  tax_number?: ExtractedField;
  vat_id?: ExtractedField;
  recipient?: ExtractedField;
  issuer?: ExtractedField;
  net_amount?: ExtractedField;
  tax_rate?: ExtractedField;
  tax_amount?: ExtractedField;
  gross_amount?: ExtractedField;
  payment_terms?: ExtractedField;
  bank_details?: ExtractedField;
  iban?: ExtractedField;
  bic?: ExtractedField;
  reference?: ExtractedField;
}

// Order-specific fields (German business order documents)
export interface OrderData {
  order_number?: ExtractedField;      // Bestellnummer
  order_date?: ExtractedField;        // Bestelldatum
  delivery_date?: ExtractedField;     // Lieferdatum
  delivery_address?: ExtractedField;  // Lieferanschrift
  billing_address?: ExtractedField;   // Rechnungsanschrift
  customer_number?: ExtractedField;   // Kundennummer
  supplier?: ExtractedField;          // Lieferant
  items?: OrderItem[];                // Positionen
  subtotal?: ExtractedField;          // Zwischensumme
  shipping_cost?: ExtractedField;     // Versandkosten
  total?: ExtractedField;             // Gesamtbetrag
  payment_method?: ExtractedField;    // Zahlungsart
  notes?: ExtractedField;             // Anmerkungen
}

export interface OrderItem {
  position: number;
  article_number?: string;    // Artikelnummer
  description: string;        // Beschreibung
  quantity: number;           // Menge
  unit?: string;              // Einheit
  unit_price?: number;        // Einzelpreis
  total_price?: number;       // Gesamtpreis
  confidence: number;
}

// Contract-specific fields (from entity_extraction_agent.py CONTRACT_FIELD_PATTERNS)
export interface ContractData {
  contract_date?: ExtractedField;     // Vertragsdatum
  start_date?: ExtractedField;        // Vertragsbeginn
  end_date?: ExtractedField;          // Vertragsende
  notice_period?: ExtractedField;     // Kuendigungsfrist
  contract_value?: ExtractedField;    // Vertragswert
  parties?: ExtractedField[];         // Vertragsparteien
  contract_type?: ExtractedField;     // Vertragsart
  duration?: ExtractedField;          // Laufzeit
  auto_renewal?: ExtractedField;      // Automatische Verlaengerung
  termination_notice?: ExtractedField; // Kuendigungshinweis
  governing_law?: ExtractedField;     // Anwendbares Recht
  signatures?: ContractSignature[];   // Unterschriften
}

export interface ContractSignature {
  name: string;
  role?: string;
  date?: string;
  confidence: number;
}

// Entity types from backend
export type EntityType =
  | 'DATE'
  | 'DATE_RANGE'
  | 'RELATIVE_DATE'
  | 'CURRENCY'
  | 'IBAN'
  | 'VAT_ID'
  | 'BUSINESS_TERM'
  | 'INVOICE_NUMBER'
  | 'TAX_NUMBER'
  | 'EMAIL'
  | 'PHONE'
  | 'POSTAL_CODE'
  | 'ADDRESS'
  | 'PERSON'
  | 'ORGANIZATION'
  | 'CONTRACT_FIELD';

// Generic entity from backend
export interface ExtractedEntity {
  type: EntityType;
  value: string;
  confidence: number;
  german_label?: string;
  field_name?: string;
  validated?: boolean;
  source?: string;
  start?: number;
  end?: number;
  // Additional fields based on type
  formatted?: string;
  numeric_value?: number;
  currency?: string;
  country?: string;
  structured?: Record<string, unknown>;
}

// Complete extracted data response
export interface ExtractedDataResponse {
  document_id: string;
  document_type: DocumentType;
  extraction_timestamp: string;
  ocr_backend: string;
  overall_confidence: number;

  // Type-specific data
  invoice_data?: InvoiceData;
  order_data?: OrderData;
  contract_data?: ContractData;

  // Generic entities
  entities: ExtractedEntity[];
  entity_count: number;
  critical_entities: ExtractedEntity[];

  // Addresses
  addresses?: ExtractedEntity[];

  // Review status
  needs_review: boolean;
  reviewed_at?: string;
  reviewed_by?: string;
}

// Field update request
export interface FieldUpdateRequest {
  document_id: string;
  field_path: string;  // e.g., "invoice_data.invoice_number"
  new_value: string;
  reason?: string;
}

// Review action
export interface ReviewAction {
  document_id: string;
  action: 'approve' | 'reject' | 'edit';
  corrections?: FieldUpdateRequest[];
  notes?: string;
}

// Field display configuration
export interface FieldConfig {
  key: string;
  label: string;
  german_label: string;
  type: 'text' | 'date' | 'currency' | 'number' | 'iban' | 'vat';
  editable: boolean;
  required: boolean;
  validation?: RegExp;
}

// Invoice field configs
export const INVOICE_FIELD_CONFIGS: FieldConfig[] = [
  { key: 'invoice_number', label: 'Invoice Number', german_label: 'Rechnungsnummer', type: 'text', editable: true, required: true },
  { key: 'invoice_date', label: 'Invoice Date', german_label: 'Rechnungsdatum', type: 'date', editable: true, required: true },
  { key: 'service_period', label: 'Service Period', german_label: 'Leistungszeitraum', type: 'text', editable: true, required: false },
  { key: 'issuer', label: 'Issuer', german_label: 'Rechnungssteller', type: 'text', editable: true, required: true },
  { key: 'recipient', label: 'Recipient', german_label: 'Rechnungsempfaenger', type: 'text', editable: true, required: true },
  { key: 'net_amount', label: 'Net Amount', german_label: 'Nettobetrag', type: 'currency', editable: true, required: true },
  { key: 'tax_rate', label: 'Tax Rate', german_label: 'Steuersatz', type: 'text', editable: true, required: false },
  { key: 'tax_amount', label: 'Tax Amount', german_label: 'Steuerbetrag', type: 'currency', editable: true, required: false },
  { key: 'gross_amount', label: 'Gross Amount', german_label: 'Bruttobetrag', type: 'currency', editable: true, required: true },
  { key: 'vat_id', label: 'VAT ID', german_label: 'USt-IdNr', type: 'vat', editable: true, required: false },
  { key: 'tax_number', label: 'Tax Number', german_label: 'Steuernummer', type: 'text', editable: true, required: false },
  { key: 'iban', label: 'IBAN', german_label: 'IBAN', type: 'iban', editable: true, required: false },
  { key: 'bic', label: 'BIC', german_label: 'BIC', type: 'text', editable: true, required: false },
  { key: 'payment_terms', label: 'Payment Terms', german_label: 'Zahlungsziel', type: 'text', editable: true, required: false },
  { key: 'reference', label: 'Reference', german_label: 'Verwendungszweck', type: 'text', editable: true, required: false },
];

// Order field configs
export const ORDER_FIELD_CONFIGS: FieldConfig[] = [
  { key: 'order_number', label: 'Order Number', german_label: 'Bestellnummer', type: 'text', editable: true, required: true },
  { key: 'order_date', label: 'Order Date', german_label: 'Bestelldatum', type: 'date', editable: true, required: true },
  { key: 'delivery_date', label: 'Delivery Date', german_label: 'Lieferdatum', type: 'date', editable: true, required: false },
  { key: 'customer_number', label: 'Customer Number', german_label: 'Kundennummer', type: 'text', editable: true, required: false },
  { key: 'supplier', label: 'Supplier', german_label: 'Lieferant', type: 'text', editable: true, required: true },
  { key: 'delivery_address', label: 'Delivery Address', german_label: 'Lieferanschrift', type: 'text', editable: true, required: false },
  { key: 'billing_address', label: 'Billing Address', german_label: 'Rechnungsanschrift', type: 'text', editable: true, required: false },
  { key: 'subtotal', label: 'Subtotal', german_label: 'Zwischensumme', type: 'currency', editable: true, required: false },
  { key: 'shipping_cost', label: 'Shipping Cost', german_label: 'Versandkosten', type: 'currency', editable: true, required: false },
  { key: 'total', label: 'Total', german_label: 'Gesamtbetrag', type: 'currency', editable: true, required: true },
  { key: 'payment_method', label: 'Payment Method', german_label: 'Zahlungsart', type: 'text', editable: true, required: false },
  { key: 'notes', label: 'Notes', german_label: 'Anmerkungen', type: 'text', editable: true, required: false },
];

// Contract field configs
export const CONTRACT_FIELD_CONFIGS: FieldConfig[] = [
  { key: 'contract_date', label: 'Contract Date', german_label: 'Vertragsdatum', type: 'date', editable: true, required: true },
  { key: 'start_date', label: 'Start Date', german_label: 'Vertragsbeginn', type: 'date', editable: true, required: true },
  { key: 'end_date', label: 'End Date', german_label: 'Vertragsende', type: 'date', editable: true, required: false },
  { key: 'notice_period', label: 'Notice Period', german_label: 'Kuendigungsfrist', type: 'text', editable: true, required: false },
  { key: 'contract_value', label: 'Contract Value', german_label: 'Vertragswert', type: 'currency', editable: true, required: false },
  { key: 'contract_type', label: 'Contract Type', german_label: 'Vertragsart', type: 'text', editable: true, required: false },
  { key: 'duration', label: 'Duration', german_label: 'Laufzeit', type: 'text', editable: true, required: false },
  { key: 'auto_renewal', label: 'Auto Renewal', german_label: 'Automatische Verlaengerung', type: 'text', editable: true, required: false },
  { key: 'termination_notice', label: 'Termination Notice', german_label: 'Kuendigungshinweis', type: 'text', editable: true, required: false },
  { key: 'governing_law', label: 'Governing Law', german_label: 'Anwendbares Recht', type: 'text', editable: true, required: false },
];

// Utility functions
export function getConfidenceLevel(confidence: number): ConfidenceLevel {
  if (confidence >= 0.85) return 'high';
  if (confidence >= 0.6) return 'medium';
  return 'low';
}

export function getConfidenceColor(confidence: number): string {
  const level = getConfidenceLevel(confidence);
  switch (level) {
    case 'high': return 'text-green-600';
    case 'medium': return 'text-yellow-600';
    case 'low': return 'text-red-600';
  }
}

export function getConfidenceBgColor(confidence: number): string {
  const level = getConfidenceLevel(confidence);
  switch (level) {
    case 'high': return 'bg-green-100';
    case 'medium': return 'bg-yellow-100';
    case 'low': return 'bg-red-100';
  }
}

export function formatCurrency(value: string | number): string {
  if (typeof value === 'number') {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(value);
  }
  return value;
}

export function formatDate(value: string): string {
  // Already in German format (DD.MM.YYYY)
  if (/^\d{1,2}\.\d{1,2}\.\d{4}$/.test(value)) {
    return value;
  }
  // ISO format conversion
  try {
    const date = new Date(value);
    return date.toLocaleDateString('de-DE');
  } catch {
    return value;
  }
}
