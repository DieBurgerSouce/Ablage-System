/**
 * Cash/Kassenbuch Model Types
 *
 * Typen für GoBD-konforme Kassenbuchfuehrung.
 *
 * WICHTIG: CashEntry ist APPEND-ONLY!
 * - Keine Updates oder Deletes
 * - Stornierung nur durch Gegenbuchung
 */

// ==================== Enums ====================

/**
 * Kassenbucheintrag-Typ
 */
export type CashEntryType =
  | 'income'           // Einnahme
  | 'deposit'          // Einlage (aus Bank)
  | 'expense'          // Ausgabe
  | 'withdrawal'       // Entnahme (an Bank)
  | 'entertainment'    // Bewirtung
  | 'travel'           // Reisekosten
  | 'office'           // Buerokosten
  | 'fuel'             // Tankkosten
  | 'parking'          // Parkgebühren
  | 'postage'          // Porto
  | 'tips'             // Trinkgeld
  | 'gifts'            // Geschenke
  | 'difference_plus'  // Kassendifferenz (+)
  | 'difference_minus' // Kassendifferenz (-)
  | 'cancellation'     // Stornobuchung
  | 'opening';         // Eröffnungsbuchung

// ==================== Cash Register ====================

/**
 * Kasse
 */
export interface CashRegister {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  current_balance: number;
  currency: string;
  is_active: boolean;
  last_entry_date: string | null;
  last_count_date: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Kasse erstellen
 */
export interface CashRegisterCreate {
  name: string;
  description?: string;
  initial_balance?: number;
  currency?: string;
}

/**
 * Kasse aktualisieren
 */
export interface CashRegisterUpdate {
  name?: string;
  description?: string;
  is_active?: boolean;
}

/**
 * Kassenliste Response
 */
export interface CashRegisterListResponse {
  registers: CashRegister[];
  total: number;
}

// ==================== Cash Entry ====================

/**
 * Bewirtungskosten-Daten
 */
export interface EntertainmentData {
  occasion: string;
  attendees: string[];
  business_reason: string;
  host_company: string;
  location?: string;
  date?: string;
}

/**
 * Kassenbucheintrag
 */
export interface CashEntry {
  id: string;
  register_id: string;
  entry_number: number;
  entry_date: string;
  entry_type: CashEntryType;
  amount: number;
  net_amount: number | null;
  tax_amount: number | null;
  tax_rate: number | null;
  balance_after: number;
  description: string;
  category_id: string | null;
  category_name: string | null;
  receipt_number: string | null;
  counterparty: string | null;
  is_entertainment: boolean;
  entertainment_data: EntertainmentData | null;
  is_cancelled: boolean;
  cancelled_by_id: string | null;
  cancels_entry_id: string | null;
  skr03_account: string | null;
  skr04_account: string | null;
  created_by_id: string;
  created_at: string;
}

/**
 * Kassenbucheintrag erstellen
 */
export interface CashEntryCreate {
  register_id: string;
  entry_date: string;
  entry_type: CashEntryType;
  amount: number;
  description: string;
  category_id?: string;
  receipt_number?: string;
  counterparty?: string;
  tax_rate?: number;
  is_entertainment?: boolean;
  entertainment_data?: EntertainmentData;
}

/**
 * Kassenbucheintrag stornieren
 */
export interface CashEntryCancelRequest {
  reason: string;
  cancel_date?: string;
}

/**
 * Kassenbucheinträge Response
 */
export interface CashEntryListResponse {
  entries: CashEntry[];
  total: number;
}

/**
 * Duplikat-Prüfung Ergebnis
 */
export interface DuplicateCheckResult {
  is_duplicate: boolean;
  existing_entry: {
    id: string;
    entry_number: number;
    entry_date: string | null;
    amount: number;
    description: string | null;
    created_at: string | null;
  } | null;
  message: string | null;
}

// ==================== Cash Category ====================

/**
 * Kassenbuch-Kategorie
 */
export interface CashCategory {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  skr03_account: string | null;
  skr04_account: string | null;
  default_tax_rate: number | null;
  is_entertainment: boolean;
  is_system: boolean;
  is_active: boolean;
  created_at: string;
}

/**
 * Kategorie erstellen
 */
export interface CashCategoryCreate {
  name: string;
  description?: string;
  skr03_account?: string;
  skr04_account?: string;
  default_tax_rate?: number;
  is_entertainment?: boolean;
}

// ==================== Cash Count (Kassensturz) ====================

/**
 * Stueckelung-Details
 */
export interface DenominationDetails {
  // Scheine
  note_500?: number;
  note_200?: number;
  note_100?: number;
  note_50?: number;
  note_20?: number;
  note_10?: number;
  note_5?: number;
  // Muenzen
  coin_200?: number;
  coin_100?: number;
  coin_50?: number;
  coin_20?: number;
  coin_10?: number;
  coin_5?: number;
  coin_2?: number;
  coin_1?: number;
}

/**
 * Kassensturz-Protokoll
 */
export interface CashCount {
  id: string;
  register_id: string;
  count_date: string;
  count_time: string;
  expected_balance: number;
  counted_balance: number;
  difference: number;
  denomination_details: DenominationDetails | null;
  notes: string | null;
  adjustment_entry_id: string | null;
  counted_by_id: string;
  created_at: string;
}

/**
 * Kassensturz durchführen
 */
export interface CashCountCreate {
  register_id: string;
  count_date?: string;
  count_time?: string;
  counted_balance: number;
  denomination_details?: DenominationDetails;
  notes?: string;
}

/**
 * Kassensturz-Liste Response
 */
export interface CashCountListResponse {
  counts: CashCount[];
  total: number;
}

// ==================== Summaries ====================

/**
 * Kassenbuch-Zusammenfassung
 */
export interface CashBookSummary {
  register_id: string;
  register_name: string;
  period_start: string | null;
  period_end: string | null;
  opening_balance: number;
  total_income: number;
  total_expense: number;
  closing_balance: number;
  entry_count: number;
  entertainment_total: number;
  entertainment_deductible: number;
}

/**
 * Tagesabschluss
 */
export interface DailySummary {
  date: string;
  opening_balance: number;
  total_income: number;
  total_expense: number;
  closing_balance: number;
  entry_count: number;
}
