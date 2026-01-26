/**
 * Company Model Types
 *
 * Typen fuer Multi-Mandanten Firmenverwaltung.
 * Unterstuetzt 20+ Mandanten mit vollstaendiger Tenant-Isolation.
 */

// ==================== Enums ====================

/**
 * Rollen in einer Firma
 */
export type CompanyRole = 'owner' | 'admin' | 'member' | 'viewer';

/**
 * Kontenrahmen
 */
export type AccountChart = 'SKR03' | 'SKR04';

// ==================== Company ====================

/**
 * Firma (vollstaendiges Model)
 */
export interface Company {
  id: string;
  name: string;
  short_name: string | null;
  display_name: string | null;

  // Rechtsform & Register
  legal_form: string | null;
  commercial_register: string | null;
  court: string | null;

  // Steuer
  vat_id: string | null;
  tax_number: string | null;

  // Adresse
  street: string | null;
  street_number: string | null;
  postal_code: string | null;
  city: string | null;
  country: string;

  // Kontakt
  email: string | null;
  phone: string | null;
  website: string | null;

  // Banking
  iban: string | null;
  bic: string | null;
  bank_name: string | null;

  // Alternative Namen fuer OCR-Erkennung
  alternative_names: string[];

  // Einstellungen
  default_currency: string;
  fiscal_year_start: number;
  kontenrahmen: AccountChart;

  // Status
  is_active: boolean;
  is_default: boolean;

  // Audit
  created_at: string;
  updated_at: string;
}

/**
 * Firma erstellen
 */
export interface CompanyCreate {
  name: string;
  short_name?: string;
  display_name?: string;

  legal_form?: string;
  commercial_register?: string;
  court?: string;

  vat_id?: string;
  tax_number?: string;

  street?: string;
  street_number?: string;
  postal_code?: string;
  city?: string;
  country?: string;

  email?: string;
  phone?: string;
  website?: string;

  iban?: string;
  bic?: string;
  bank_name?: string;

  alternative_names?: string[];

  default_currency?: string;
  fiscal_year_start?: number;
  kontenrahmen?: AccountChart;
}

/**
 * Firma aktualisieren
 */
export interface CompanyUpdate extends Partial<CompanyCreate> {
  is_active?: boolean;
  is_default?: boolean;
}

/**
 * Firmenliste Response
 */
export interface CompanyListResponse {
  items: Company[];
  total: number;
  current_company_id: string | null;
}

// ==================== UserCompany ====================

/**
 * Benutzer-Firma-Zuordnung
 */
export interface UserCompany {
  id: string;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  company_id: string;
  role: CompanyRole;
  can_manage_cash: boolean;
  can_approve_expenses: boolean;
  can_export_datev: boolean;
  can_manage_settings: boolean;
  is_current: boolean;
  created_at: string;
}

/**
 * Benutzer zu Firma hinzufuegen
 */
export interface UserCompanyCreate {
  user_id: string;
  role?: CompanyRole;
  can_manage_cash?: boolean;
  can_approve_expenses?: boolean;
  can_export_datev?: boolean;
  can_manage_settings?: boolean;
}

/**
 * Benutzerrolle aktualisieren
 */
export interface UserCompanyUpdate {
  role?: CompanyRole;
  can_manage_cash?: boolean;
  can_approve_expenses?: boolean;
  can_export_datev?: boolean;
  can_manage_settings?: boolean;
}

// ==================== Labels ====================

export const COMPANY_ROLE_LABELS: Record<CompanyRole, string> = {
  owner: 'Inhaber',
  admin: 'Administrator',
  member: 'Mitarbeiter',
  viewer: 'Nur Lesen',
};

export const LEGAL_FORM_OPTIONS = [
  { value: 'GmbH', label: 'GmbH' },
  { value: 'UG', label: 'UG (haftungsbeschraenkt)' },
  { value: 'AG', label: 'AG' },
  { value: 'KG', label: 'KG' },
  { value: 'OHG', label: 'OHG' },
  { value: 'GbR', label: 'GbR' },
  { value: 'Einzelunternehmen', label: 'Einzelunternehmen' },
  { value: 'e.V.', label: 'Eingetragener Verein (e.V.)' },
];

export const KONTENRAHMEN_OPTIONS = [
  { value: 'SKR03', label: 'SKR03' },
  { value: 'SKR04', label: 'SKR04' },
];

// ==================== Company Metrics ====================

/**
 * Metriken fuer Company Dashboard
 */
export interface CompanyMetrics {
  /** Anzahl aktiver Dokumente */
  document_count: number;
  /** Anzahl offener Rechnungen */
  open_invoice_count: number;
  /** Gesamtbetrag offener Rechnungen */
  open_invoice_amount: number;
  /** Anzahl ueberfaelliger Rechnungen */
  overdue_invoice_count: number;
  /** Gesamtbetrag ueberfaelliger Rechnungen */
  overdue_invoice_amount: number;
  /** Anzahl Dokumente in Verarbeitung */
  processing_count: number;
  /** Anzahl Dokumente mit Fehlern */
  error_count: number;
  /** Durchschnittliche OCR-Confidence */
  average_ocr_confidence: number;
  /** Anzahl aktiver Benutzer */
  active_user_count: number;
  /** Speicherverbrauch in Bytes */
  storage_used_bytes: number;
  /** Letzte Aktivitaet */
  last_activity_at: string | null;
}

/**
 * Zeitraum fuer Metriken
 */
export type MetricsPeriod = '7d' | '30d' | '90d' | '1y' | 'all';

// ==================== Dashboard Alerts ====================

/**
 * Schweregrad eines Alerts
 */
export type AlertSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';

/**
 * Kategorie eines Alerts
 */
export type AlertCategory =
  | 'fraud'
  | 'risk'
  | 'compliance'
  | 'deadline'
  | 'system'
  | 'security'
  | 'quality'
  | 'workflow';

/**
 * Status eines Alerts
 */
export type AlertStatus = 'new' | 'acknowledged' | 'in_progress' | 'resolved' | 'dismissed' | 'escalated';

/**
 * Dashboard Alert
 */
export interface DashboardAlert {
  id: string;
  alert_code: string;
  title: string;
  message: string;
  category: AlertCategory;
  severity: AlertSeverity;
  status: AlertStatus;
  document_id: string | null;
  entity_id: string | null;
  metadata: Record<string, unknown>;
  context: Record<string, unknown>;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  auto_dismiss_at: string | null;
}

/**
 * Alert-Zusammenfassung fuer Dashboard
 */
export interface AlertSummary {
  total: number;
  new_count: number;
  critical_count: number;
  high_count: number;
  by_category: Record<AlertCategory, number>;
  recent: DashboardAlert[];
}

// ==================== Dashboard Summary ====================

/**
 * Zusammenfassung fuer Company Dashboard
 */
export interface DashboardSummary {
  /** Firma */
  company: Company;
  /** Metriken */
  metrics: CompanyMetrics;
  /** Alert-Zusammenfassung */
  alerts: AlertSummary;
  /** Aktuelle Periode */
  period: MetricsPeriod;
  /** Generiert am */
  generated_at: string;
}

/**
 * Trend-Indikator
 */
export type TrendDirection = 'up' | 'down' | 'stable';

/**
 * Metrik mit Trend
 */
export interface TrendMetric {
  value: number;
  previous_value: number;
  change_percent: number;
  trend: TrendDirection;
}

/**
 * Dashboard KPIs mit Trends
 */
export interface DashboardKPIs {
  revenue: TrendMetric;
  expenses: TrendMetric;
  outstanding: TrendMetric;
  documents_processed: TrendMetric;
  ocr_accuracy: TrendMetric;
  average_processing_time_ms: TrendMetric;
}
