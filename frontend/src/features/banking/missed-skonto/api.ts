/**
 * Missed Skonto API
 * API-Funktionen für verpasste Skonto-Daten
 */

import { api } from '@/lib/api';
import type {
  MissedSkontoResponse,
  MissedSkontoFilters,
  SkontoStatistics,
  MonthlySkontoSummary,
} from './types';

const API_BASE = '/api/v1/invoices';

/**
 * Verpasste Skonto-Möglichkeiten abrufen
 */
export async function getMissedSkonto(
  filters: MissedSkontoFilters = {}
): Promise<MissedSkontoResponse> {
  const params = new URLSearchParams();

  if (filters.startDate) params.set('start_date', filters.startDate);
  if (filters.endDate) params.set('end_date', filters.endDate);
  if (filters.entityId) params.set('entity_id', filters.entityId);
  if (filters.minAmount) params.set('min_amount', String(filters.minAmount));
  if (filters.page) params.set('page', String(filters.page));
  if (filters.perPage) params.set('per_page', String(filters.perPage));

  const response = await api.get(`${API_BASE}/skonto/missed?${params}`);
  const data = response.data;

  return {
    items: (data.items || []).map((item: Record<string, unknown>) => ({
      invoiceId: String(item.invoice_id || ''),
      invoiceNumber: String(item.invoice_number || ''),
      documentId: String(item.document_id || ''),
      entityId: item.entity_id ? String(item.entity_id) : undefined,
      entityName: String(item.entity_name || 'Unbekannt'),
      invoiceDate: String(item.invoice_date || ''),
      amount: Number(item.amount || 0),
      skontoPercentage: Number(item.skonto_percentage || 0),
      skontoAmount: Number(item.skonto_amount || 0),
      skontoDeadline: String(item.skonto_deadline || ''),
      daysMissedBy: Number(item.days_missed_by || 0),
      paidAt: item.paid_at ? String(item.paid_at) : undefined,
      paidAmount: item.paid_amount ? Number(item.paid_amount) : undefined,
    })),
    total: Number(data.total || 0),
    totalMissedAmount: Number(data.total_missed_amount || 0),
  };
}

/**
 * Skonto-Statistiken für einen Zeitraum abrufen
 */
export async function getSkontoStatistics(
  startDate: string,
  endDate: string
): Promise<SkontoStatistics> {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
  });

  const response = await api.get(`${API_BASE}/skonto/statistics?${params}`);
  const data = response.data;

  return {
    periodStart: String(data.period_start || startDate),
    periodEnd: String(data.period_end || endDate),
    totalInvoices: Number(data.total_invoices || 0),
    invoicesWithSkonto: Number(data.invoices_with_skonto || 0),
    skontoUsedCount: Number(data.skonto_used_count || 0),
    skontoMissedCount: Number(data.skonto_missed_count || 0),
    skontoPendingCount: Number(data.skonto_pending_count || 0),
    totalSavings: Number(data.total_savings || 0),
    missedSavings: Number(data.missed_savings || 0),
    potentialSavings: Number(data.potential_savings || 0),
    usageRate: Number(data.usage_rate || 0),
  };
}

/**
 * Monatliche Skonto-Zusammenfassung abrufen
 */
export async function getMonthlySkontoSummary(
  months: number = 12
): Promise<MonthlySkontoSummary[]> {
  const params = new URLSearchParams({
    months: String(months),
  });

  const response = await api.get(`${API_BASE}/skonto/monthly-summary?${params}`);
  const data = response.data;

  return (data.summaries || data || []).map((item: Record<string, unknown>) => ({
    month: String(item.month || ''),
    year: Number(item.year || 0),
    usedCount: Number(item.used_count || 0),
    missedCount: Number(item.missed_count || 0),
    usedAmount: Number(item.used_amount || 0),
    missedAmount: Number(item.missed_amount || 0),
    usageRate: Number(item.usage_rate || 0),
  }));
}

/**
 * Export verpasste Skonto als Excel/CSV
 */
export async function exportMissedSkonto(
  format: 'xlsx' | 'csv',
  filters: MissedSkontoFilters = {}
): Promise<Blob> {
  const params = new URLSearchParams({ format });

  if (filters.startDate) params.set('start_date', filters.startDate);
  if (filters.endDate) params.set('end_date', filters.endDate);
  if (filters.entityId) params.set('entity_id', filters.entityId);

  const response = await api.get(`${API_BASE}/skonto/missed/export?${params}`, {
    responseType: 'blob',
  });

  return response.data;
}
