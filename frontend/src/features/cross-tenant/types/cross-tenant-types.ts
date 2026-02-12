/**
 * Cross-Tenant Reports Types
 *
 * TypeScript-Definitionen für mandantenübergreifende Berichte.
 * Spiegelt die Backend-Pydantic-Modelle aus cross_tenant_reports.py.
 */

// =============================================================================
// Company Overview
// =============================================================================

export interface CompanyOverviewStats {
  company_id: string;
  company_name: string;
  is_active: boolean;
  total_documents: number;
  documents_this_month: number;
  archived_documents: number;
  last_upload_date: string | null;
}

export interface CrossTenantOverviewResponse {
  total_companies: number;
  active_companies: number;
  companies: CompanyOverviewStats[];
}

// =============================================================================
// Company Financial Summary
// =============================================================================

export interface CompanyFinancialSummary {
  company_id: string;
  company_name: string;
  is_active: boolean;
  total_invoices: number;
  processing_queued: number;
  processing_completed: number;
  processing_failed: number;
}

export interface CrossTenantFinancialResponse {
  total_companies: number;
  active_companies: number;
  companies: CompanyFinancialSummary[];
}

// =============================================================================
// Sorting
// =============================================================================

export type SortDirection = 'asc' | 'desc';

export interface SortConfig<T extends string> {
  column: T;
  direction: SortDirection;
}

export type OverviewSortColumn =
  | 'company_name'
  | 'total_documents'
  | 'documents_this_month'
  | 'archived_documents'
  | 'last_upload_date';

export type FinancialSortColumn =
  | 'company_name'
  | 'total_invoices'
  | 'processing_queued'
  | 'processing_completed'
  | 'processing_failed';

// =============================================================================
// Filter
// =============================================================================

export type ActiveFilter = 'all' | 'active' | 'inactive';
