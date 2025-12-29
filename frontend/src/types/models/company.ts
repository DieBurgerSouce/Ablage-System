/**
 * Company Model Types
 *
 * Typen für Multi-Mandanten Firmenverwaltung.
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
 * Firma
 */
export interface Company {
  id: string;
  name: string;
  vat_id: string | null;
  tax_number: string | null;
  address_street: string | null;
  address_city: string | null;
  address_postal_code: string | null;
  address_country: string;
  email: string | null;
  phone: string | null;
  website: string | null;
  account_chart: AccountChart;
  fiscal_year_start_month: number;
  settings: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * Firma erstellen
 */
export interface CompanyCreate {
  name: string;
  vat_id?: string;
  tax_number?: string;
  address_street?: string;
  address_city?: string;
  address_postal_code?: string;
  address_country?: string;
  email?: string;
  phone?: string;
  website?: string;
  account_chart?: AccountChart;
  fiscal_year_start_month?: number;
  settings?: Record<string, unknown>;
}

/**
 * Firma aktualisieren
 */
export interface CompanyUpdate {
  name?: string;
  vat_id?: string;
  tax_number?: string;
  address_street?: string;
  address_city?: string;
  address_postal_code?: string;
  address_country?: string;
  email?: string;
  phone?: string;
  website?: string;
  account_chart?: AccountChart;
  fiscal_year_start_month?: number;
  settings?: Record<string, unknown>;
  is_active?: boolean;
}

/**
 * Firmenliste Response
 */
export interface CompanyListResponse {
  companies: Company[];
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
  is_current: boolean;
  created_at: string;
}

/**
 * Benutzer zu Firma hinzufügen
 */
export interface UserCompanyCreate {
  user_id: string;
  role?: CompanyRole;
  can_manage_cash?: boolean;
  can_approve_expenses?: boolean;
}

/**
 * Benutzerrolle aktualisieren
 */
export interface UserCompanyUpdate {
  role?: CompanyRole;
  can_manage_cash?: boolean;
  can_approve_expenses?: boolean;
}
