/**
 * Recurring Invoice (Abo-Rechnungen) Types
 *
 * TypeScript Typen für das Abo-Rechnungen Feature.
 * Konsistent mit Backend-Schema: RecurringInvoice Model und API Responses.
 */

// ==================== Status Enums ====================

export type RecurringInvoiceStatus = 'active' | 'paused' | 'cancelled' | 'expired';

export type RecurringIntervalType = 'monthly' | 'quarterly' | 'half_yearly' | 'yearly';

export type DetectionMethod = 'auto' | 'manual';

export type OccurrenceStatus =
  | 'expected'
  | 'matched'
  | 'missing'
  | 'late'
  | 'overpaid'
  | 'underpaid';

// ==================== Core Types ====================

/**
 * Preis-Historyeintrag
 */
export interface PriceHistoryEntry {
  date: string | null;
  amount: number | null;
  change_percent: number | null;
}

/**
 * Einzelne Abo-Rechnung (API Response)
 */
export interface RecurringInvoiceResponse {
  id: string;
  company_id: string;
  vendor_entity_id: string | null;
  vendor_name: string;
  interval_type: RecurringIntervalType;
  interval_months: number;
  expected_amount: number;
  currency: string;
  tolerance_percent: number;
  first_seen_date: string | null;
  last_seen_date: string | null;
  next_expected_date: string | null;
  cancellation_deadline: string | null;
  notice_period_days: number | null;
  auto_renewal: boolean;
  detection_confidence: number;
  detection_method: DetectionMethod;
  match_count: number;
  price_history: PriceHistoryEntry[];
  last_price_change_date: string | null;
  price_change_percent: number | null;
  status: RecurringInvoiceStatus;
  price_increase_alerted: boolean;
  missing_invoice_alerted: boolean;
  category: string | null;
  description: string | null;
  document_type: string | null;
  reference_pattern: string | null;
  created_at: string;
  updated_at: string | null;
}

/**
 * Occurrence (Soll/Ist-Eintrag)
 */
export interface OccurrenceResponse {
  id: string;
  recurring_invoice_id: string;
  document_id: string | null;
  invoice_tracking_id: string | null;
  expected_date: string;
  actual_date: string | null;
  expected_amount: number;
  actual_amount: number | null;
  amount_deviation: number | null;
  status: OccurrenceStatus;
  match_confidence: number | null;
  matched_at: string | null;
  matched_by: string | null;
  period_start: string | null;
  period_end: string | null;
  notes: string | null;
  created_at: string;
}

/**
 * Detail Response (mit Occurrences)
 */
export interface RecurringInvoiceDetailResponse extends RecurringInvoiceResponse {
  occurrences: OccurrenceResponse[];
}

/**
 * Paginierte Listen-Response
 */
export interface RecurringInvoiceListResponse {
  items: RecurringInvoiceResponse[];
  total: number;
  page: number;
  page_size: number;
}

// ==================== Detection / Alert Types ====================

/**
 * Erkanntes Muster (Pattern Detection)
 */
export interface DetectedPatternResponse {
  vendor_name: string;
  vendor_entity_id: string | null;
  interval_type: RecurringIntervalType;
  interval_months: number;
  average_amount: number;
  occurrences_found: number;
  confidence: number;
  first_date: string;
  last_date: string;
}

/**
 * Fehlende Rechnung
 */
export interface MissingInvoiceResponse {
  recurring_invoice_id: string;
  vendor_name: string;
  expected_date: string;
  expected_amount: number;
  days_overdue: number;
}

/**
 * Preisänderung
 */
export interface PriceChangeResponse {
  recurring_invoice_id: string;
  vendor_name: string;
  old_amount: number;
  new_amount: number;
  change_percent: number;
  change_date: string;
}

// ==================== Soll/Ist Report ====================

/**
 * Einzelne Zeile im Soll/Ist-Bericht
 */
export interface SollIstRowResponse {
  recurring_invoice_id: string;
  vendor_name: string;
  category: string | null;
  expected_amount: number;
  actual_amount: number | null;
  deviation: number | null;
  deviation_percent: number | null;
  status: string;
  expected_date: string;
  actual_date: string | null;
}

/**
 * Soll/Ist Gesamtbericht
 */
export interface SollIstReportResponse {
  company_id: string;
  year: number;
  month: number;
  rows: SollIstRowResponse[];
  total_expected: number;
  total_actual: number;
  total_deviation: number;
  missing_count: number;
  matched_count: number;
  generated_at: string;
}

// ==================== Create/Update Types ====================

/**
 * Payload für manuelle Abo-Erstellung
 */
export interface RecurringInvoiceCreate {
  vendor_name: string;
  interval_type: RecurringIntervalType;
  expected_amount: number;
  currency?: string;
  category?: string;
  description?: string;
  cancellation_deadline?: string;
  notice_period_days?: number;
  auto_renewal?: boolean;
  tolerance_percent?: number;
  reference_pattern?: string;
}

/**
 * Payload für Abo-Update
 */
export interface RecurringInvoiceUpdate {
  vendor_name?: string;
  interval_type?: RecurringIntervalType;
  expected_amount?: number;
  currency?: string;
  status?: RecurringInvoiceStatus;
  category?: string;
  description?: string;
  cancellation_deadline?: string;
  notice_period_days?: number;
  auto_renewal?: boolean;
  tolerance_percent?: number;
  reference_pattern?: string;
}

// ==================== Filter Types ====================

/**
 * Filter für Abo-Liste
 */
export interface RecurringInvoiceFilter {
  status?: RecurringInvoiceStatus;
  page?: number;
  page_size?: number;
}

/**
 * Parameter für Muster-Erkennung
 */
export interface DetectPatternsParams {
  min_occurrences?: number;
  lookback_months?: number;
}

// ==================== UI Labels (Deutsch) ====================

export const INTERVAL_LABELS: Record<RecurringIntervalType, string> = {
  monthly: 'Monatlich',
  quarterly: 'Vierteljährlich',
  half_yearly: 'Halbjährlich',
  yearly: 'Jährlich',
};

export const STATUS_LABELS: Record<RecurringInvoiceStatus, string> = {
  active: 'Aktiv',
  paused: 'Pausiert',
  cancelled: 'Gekündigt',
  expired: 'Abgelaufen',
};

export const STATUS_VARIANTS: Record<
  RecurringInvoiceStatus,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  active: 'default',
  paused: 'secondary',
  cancelled: 'outline',
  expired: 'destructive',
};

export const OCCURRENCE_STATUS_LABELS: Record<OccurrenceStatus, string> = {
  expected: 'Erwartet',
  matched: 'Zugeordnet',
  missing: 'Fehlend',
  late: 'Verspätet',
  overpaid: 'Überbezahlt',
  underpaid: 'Unterbezahlt',
};

export const OCCURRENCE_STATUS_VARIANTS: Record<
  OccurrenceStatus,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  expected: 'secondary',
  matched: 'default',
  missing: 'destructive',
  late: 'destructive',
  overpaid: 'outline',
  underpaid: 'outline',
};
