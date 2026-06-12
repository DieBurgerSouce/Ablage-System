/**
 * Expense Model Types
 *
 * Typen für Spesenabrechnung mit Workflow.
 */

// ==================== Enums ====================

/**
 * Spesenabrechnung-Status
 */
export type ExpenseReportStatus =
  | 'draft'      // Entwurf
  | 'submitted'  // Eingereicht
  | 'in_review'  // In Prüfung
  | 'approved'   // Genehmigt
  | 'rejected'   // Abgelehnt
  | 'paid';      // Ausgezahlt

/**
 * Spesentyp
 */
export type ExpenseType =
  | 'receipt'    // Beleg
  | 'mileage'    // Kilometergeld
  | 'per_diem'   // Verpflegungspauschale
  | 'flat_rate'; // Pauschale

// ==================== Expense Report ====================

/**
 * Spesenabrechnung
 */
export interface ExpenseReport {
  id: string;
  company_id: string;
  title: string;
  description: string | null;
  status: ExpenseReportStatus;
  employee_id: string;
  employee_name: string | null;
  submitted_by_id: string | null;
  approved_by_id: string | null;
  period_start: string | null;
  period_end: string | null;
  purpose: string | null;
  project_code: string | null;
  cost_center: string | null;
  total_amount: number;
  approved_amount: number;
  paid_amount: number;
  rejection_reason: string | null;
  items: ExpenseItem[];
  submitted_at: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  paid_at: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Spesenabrechnung erstellen
 */
export interface ExpenseReportCreate {
  title: string;
  description?: string;
  employee_id?: string;
  period_start?: string;
  period_end?: string;
  purpose?: string;
  project_code?: string;
  cost_center?: string;
}

/**
 * Spesenabrechnung aktualisieren
 */
export interface ExpenseReportUpdate {
  title?: string;
  description?: string;
  period_start?: string;
  period_end?: string;
  purpose?: string;
  project_code?: string;
  cost_center?: string;
}

/**
 * Spesenabrechnungsliste Response
 */
export interface ExpenseReportListResponse {
  reports: ExpenseReport[];
  total: number;
}

// ==================== Expense Item ====================

/**
 * Bewirtungskosten-Daten (gleiche Struktur wie bei Cash)
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
 * Mahlzeiten für Verpflegungspauschale
 */
export interface MealsProvided {
  breakfast?: boolean;
  lunch?: boolean;
  dinner?: boolean;
}

/**
 * Spesenposition
 */
export interface ExpenseItem {
  id: string;
  report_id: string;
  expense_date: string;
  expense_type: ExpenseType;
  description: string;
  amount: number;
  currency: string;
  exchange_rate: number;
  amount_eur: number;
  tax_rate: number | null;
  net_amount: number | null;
  tax_amount: number | null;
  category_id: string | null;
  category_name: string | null;
  receipt_number: string | null;
  receipt_document_id: string | null;
  vendor: string | null;
  is_entertainment: boolean;
  entertainment_data: EntertainmentData | null;
  mileage_km: number | null;
  mileage_from: string | null;
  mileage_to: string | null;
  mileage_purpose: string | null;
  per_diem_hours: number | null;
  per_diem_meals_provided: MealsProvided | null;
  per_diem_country: string | null;
  notes: string | null;
  is_approved: boolean;
  approved_amount: number;
  deductible_amount: number;
  created_at: string;
  updated_at: string;
}

/**
 * Spesenposition erstellen
 */
export interface ExpenseItemCreate {
  expense_date: string;
  expense_type: ExpenseType;
  description: string;
  amount: number;
  currency?: string;
  exchange_rate?: number;
  tax_rate?: number;
  net_amount?: number;
  tax_amount?: number;
  category_id?: string;
  receipt_number?: string;
  receipt_document_id?: string;
  vendor?: string;
  is_entertainment?: boolean;
  entertainment_data?: EntertainmentData;
  mileage_km?: number;
  mileage_from?: string;
  mileage_to?: string;
  mileage_purpose?: string;
  per_diem_hours?: number;
  per_diem_meals_provided?: MealsProvided;
  per_diem_country?: string;
  notes?: string;
}

/**
 * Spesenposition aktualisieren
 */
export interface ExpenseItemUpdate {
  expense_date?: string;
  description?: string;
  amount?: number;
  currency?: string;
  exchange_rate?: number;
  tax_rate?: number;
  net_amount?: number;
  tax_amount?: number;
  category_id?: string;
  receipt_number?: string;
  receipt_document_id?: string;
  vendor?: string;
  notes?: string;
}

// ==================== Workflow ====================

/**
 * Spesenabrechnung genehmigen
 */
export interface ExpenseReportApproveRequest {
  approved_amount?: number;
  notes?: string;
}

/**
 * Spesenabrechnung ablehnen
 */
export interface ExpenseReportRejectRequest {
  reason: string;
}

/**
 * Spesenabrechnung auszahlen
 */
// Backend-Vertrag: ExpenseReportPayRequest (app/db/schemas.py)
export interface ExpenseReportPayRequest {
  payment_method: string;
  payment_reference?: string;
  cash_register_id?: string;
}

// ==================== Calculators ====================

/**
 * Verpflegungspauschale-Berechnung Anfrage
 */
export interface PerDiemCalculateRequest {
  travel_start: string;
  travel_end: string;
  meals_provided?: MealsProvided;
  country?: string;
}

/**
 * Verpflegungspauschale-Berechnung Ergebnis
 */
export interface PerDiemCalculation {
  travel_start: string;
  travel_end: string;
  total_hours: number;
  country: string;
  base_rate: number;
  rate_type: 'full_day' | 'partial_day' | 'arrival_departure' | 'none';
  meals_provided: MealsProvided;
  meal_reductions: number;
  meal_deductions?: number;  // Alias for meal_reductions
  full_days?: number;        // Number of full 24h days
  partial_days?: number;     // Number of arrival/departure days
  total_amount: number;
}

/**
 * Kilometergeld-Berechnung Anfrage
 */
// Backend-Vertrag: MileageCalculationRequest (kilometers + vehicle_type)
export interface MileageCalculateRequest {
  kilometers: number;
  /** 'pkw' | 'motorrad' (Backend-Konvention) */
  vehicle_type?: string;
}

/**
 * Kilometergeld-Berechnung Ergebnis
 */
export interface MileageCalculation {
  kilometers: number;
  rate_per_km: number;
  total_amount: number;
}
