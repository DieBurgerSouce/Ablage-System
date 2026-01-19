/**
 * Holding Dashboard API Client
 *
 * API-Funktionen fuer Multi-Company Holding-Sicht.
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface CompanySummary {
  id: string;
  name: string;
  short_name: string | null;
  subscription_tier: string;
  is_active: boolean;
}

export interface Financials {
  total_receivables: number;
  total_payables: number;
  net_position: number;
  overdue_receivables: number;
  overdue_payables: number;
  currency: string;
}

export interface DocumentMetrics {
  total: number;
  this_month: number;
  by_status: Record<string, number>;
}

export interface InvoiceMetrics {
  open_outgoing: number;
  open_incoming: number;
  avg_payment_days: number | null;
}

export interface BankingMetrics {
  total_balance: number;
  account_count: number;
  transactions_last_30d: number;
  currency: string;
}

export interface IntercompanyMetrics {
  total_intercompany_volume: number;
  intercompany_receivables: number;
  intercompany_payables: number;
  transaction_count: number;
}

export interface ConsolidatedOverview {
  generated_at: string;
  company_count: number;
  companies: CompanySummary[];
  financials: Financials;
  documents: DocumentMetrics;
  invoices: InvoiceMetrics;
  banking: BankingMetrics;
  intercompany: IntercompanyMetrics;
}

export interface CompanyComparisonItem {
  company_id: string;
  company_name: string;
  metric: string;
  value: number;
}

export interface CompanyComparison {
  metric: string;
  comparison_date: string;
  companies: CompanyComparisonItem[];
}

export interface CashFlowItem {
  company_id: string;
  company_name: string;
  inflows: number;
  outflows: number;
  net_flow: number;
  period: string;
}

export interface CashFlowOverview {
  period_type: string;
  total_inflows: number;
  total_outflows: number;
  total_net_flow: number;
  by_company: CashFlowItem[];
}

export type ComparisonMetric = 'documents' | 'receivables' | 'payables' | 'balance';
export type CashFlowPeriod = 'daily' | 'weekly' | 'monthly';

// ==================== API Functions ====================

/**
 * Hole konsolidierte Holding-Uebersicht
 */
export async function getHoldingOverview(
  companyIds?: string[]
): Promise<ConsolidatedOverview> {
  const params = new URLSearchParams();
  if (companyIds?.length) {
    companyIds.forEach(id => params.append('company_ids', id));
  }
  const query = params.toString();
  const url = query ? `/holding/overview?${query}` : '/holding/overview';
  const response = await apiClient.get<ConsolidatedOverview>(url);
  return response.data;
}

/**
 * Hole Liste aller Firmen
 */
export async function getHoldingCompanies(): Promise<CompanySummary[]> {
  const response = await apiClient.get<CompanySummary[]>('/holding/companies');
  return response.data;
}

/**
 * Vergleiche Firmen nach Metrik
 */
export async function compareCompanies(
  metric: ComparisonMetric,
  companyIds?: string[]
): Promise<CompanyComparison> {
  const params = new URLSearchParams();
  params.append('metric', metric);
  if (companyIds?.length) {
    companyIds.forEach(id => params.append('company_ids', id));
  }
  const response = await apiClient.get<CompanyComparison>(
    `/holding/compare?${params.toString()}`
  );
  return response.data;
}

/**
 * Hole Intercompany-Metriken
 */
export async function getIntercompanyMetrics(
  companyIds?: string[]
): Promise<IntercompanyMetrics> {
  const params = new URLSearchParams();
  if (companyIds?.length) {
    companyIds.forEach(id => params.append('company_ids', id));
  }
  const query = params.toString();
  const url = query ? `/holding/intercompany?${query}` : '/holding/intercompany';
  const response = await apiClient.get<IntercompanyMetrics>(url);
  return response.data;
}

/**
 * Hole Cashflow-Uebersicht
 */
export async function getCashFlowOverview(
  period: CashFlowPeriod = 'monthly',
  companyIds?: string[]
): Promise<CashFlowOverview> {
  const params = new URLSearchParams();
  params.append('period', period);
  if (companyIds?.length) {
    companyIds.forEach(id => params.append('company_ids', id));
  }
  const response = await apiClient.get<CashFlowOverview>(
    `/holding/cashflow?${params.toString()}`
  );
  return response.data;
}
