/**
 * Skonto API Client
 *
 * API-Funktionen für Skonto-Verwaltung.
 * Kommuniziert mit Backend /api/v1/invoices/{id}/skonto Endpoints.
 */

import { apiClient } from '@/lib/api/client';
import type {
  SkontoInfo,
  SkontoOpportunity,
  MissedSkontoResponse,
  SkontoStatistics,
  MonthlySkontoSummary,
  ApplySkontoRequest,
  SetSkontoRequest,
  MissedSkontoFilter,
} from './types';
import type { InvoiceTrackingResponse } from '@/features/invoices/types/invoice-types';

// ==================== Skonto Info ====================

/**
 * Holt Skonto-Informationen für eine Rechnung
 */
export async function getSkontoInfo(invoiceId: string): Promise<SkontoInfo> {
  const response = await apiClient.get<{
    invoice_id: string;
    skonto_percentage: number | null;
    skonto_amount: number | null;
    skonto_deadline: string | null;
    amount_with_skonto: number | null;
    days_remaining: number | null;
    is_expired: boolean;
    skonto_used: boolean;
    savings_potential: number | null;
    message?: string;
  }>(`/invoices/${invoiceId}/skonto`);

  return {
    invoiceId: response.invoice_id,
    percentage: response.skonto_percentage,
    amount: response.skonto_amount,
    deadline: response.skonto_deadline,
    amountWithSkonto: response.amount_with_skonto,
    daysRemaining: response.days_remaining,
    isExpired: response.is_expired,
    used: response.skonto_used,
    savingsPotential: response.savings_potential,
    message: response.message,
  };
}

/**
 * Setzt Skonto-Konditionen für eine Rechnung
 */
export async function setSkonto(
  invoiceId: string,
  data: SetSkontoRequest
): Promise<InvoiceTrackingResponse> {
  const params = new URLSearchParams({
    skonto_percentage: data.skontoPercentage.toString(),
  });

  if (data.skontoDays !== undefined) {
    params.append('skonto_days', data.skontoDays.toString());
  }
  if (data.netDays !== undefined) {
    params.append('net_days', data.netDays.toString());
  }

  const response = await apiClient.patch<InvoiceTrackingResponse>(
    `/invoices/${invoiceId}/skonto?${params.toString()}`
  );

  // Transform snake_case to camelCase
  return transformInvoiceResponse(response);
}

/**
 * Wendet Skonto bei einer Zahlung an
 */
export async function applySkonto(
  invoiceId: string,
  data: ApplySkontoRequest
): Promise<InvoiceTrackingResponse> {
  const params = new URLSearchParams({
    payment_amount: data.paymentAmount.toString(),
  });

  if (data.paymentDate) {
    params.append('payment_date', data.paymentDate);
  }
  if (data.forceApply !== undefined) {
    params.append('force_apply', data.forceApply.toString());
  }

  const response = await apiClient.post<InvoiceTrackingResponse>(
    `/invoices/${invoiceId}/apply-skonto?${params.toString()}`
  );

  return transformInvoiceResponse(response);
}

// ==================== Upcoming Skonto ====================

/**
 * Holt anstehende Skonto-Fristen (bald ablaufend)
 */
export async function getUpcomingSkonto(
  daysAhead: number = 7,
  limit: number = 20
): Promise<SkontoOpportunity[]> {
  const params = new URLSearchParams({
    days_ahead: daysAhead.toString(),
    limit: limit.toString(),
  });

  const response = await apiClient.get<Array<{
    invoice_id: string;
    invoice_number: string;
    entity_name: string;
    skonto_deadline: string;
    skonto_amount: number;
    days_remaining: number;
    urgency: 'critical' | 'warning' | 'info';
  }>>(`/invoices/skonto/upcoming?${params.toString()}`);

  return response.map((item) => ({
    invoiceId: item.invoice_id,
    invoiceNumber: item.invoice_number,
    entityName: item.entity_name,
    skontoDeadline: item.skonto_deadline,
    skontoAmount: item.skonto_amount,
    daysRemaining: item.days_remaining,
    urgency: item.urgency,
  }));
}

// ==================== Missed Skonto ====================

/**
 * Holt verpasste Skonto-Möglichkeiten
 */
export async function getMissedSkonto(
  filter: MissedSkontoFilter = {}
): Promise<MissedSkontoResponse> {
  const params = new URLSearchParams();

  if (filter.startDate) params.append('start_date', filter.startDate);
  if (filter.endDate) params.append('end_date', filter.endDate);
  if (filter.page) params.append('page', filter.page.toString());
  if (filter.perPage) params.append('per_page', filter.perPage.toString());

  const response = await apiClient.get<{
    items: Array<{
      invoice_id: string;
      invoice_number: string;
      document_id: string;
      entity_id: string | null;
      entity_name: string;
      invoice_date: string | null;
      amount: number;
      skonto_percentage: number;
      skonto_amount: number;
      skonto_deadline: string | null;
      days_missed_by: number;
      paid_at: string | null;
      paid_amount: number | null;
    }>;
    total: number;
    page: number;
    per_page: number;
    total_missed_amount: number;
  }>(`/invoices/skonto/missed?${params.toString()}`);

  return {
    items: response.items.map((item) => ({
      invoiceId: item.invoice_id,
      invoiceNumber: item.invoice_number,
      documentId: item.document_id,
      entityId: item.entity_id,
      entityName: item.entity_name,
      invoiceDate: item.invoice_date,
      amount: item.amount,
      skontoPercentage: item.skonto_percentage,
      skontoAmount: item.skonto_amount,
      skontoDeadline: item.skonto_deadline,
      daysMissedBy: item.days_missed_by,
      paidAt: item.paid_at,
      paidAmount: item.paid_amount,
    })),
    total: response.total,
    page: response.page,
    perPage: response.per_page,
    totalMissedAmount: response.total_missed_amount,
  };
}

// ==================== Statistics ====================

/**
 * Holt Skonto-Statistiken für einen Zeitraum
 */
export async function getSkontoStatistics(
  startDate: string,
  endDate: string
): Promise<SkontoStatistics> {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
  });

  const response = await apiClient.get<{
    period_start: string;
    period_end: string;
    total_invoices: number;
    invoices_with_skonto: number;
    skonto_used_count: number;
    skonto_missed_count: number;
    skonto_pending_count: number;
    total_savings: number;
    missed_savings: number;
    potential_savings: number;
    usage_rate: number;
  }>(`/invoices/skonto/statistics?${params.toString()}`);

  return {
    periodStart: response.period_start,
    periodEnd: response.period_end,
    totalInvoices: response.total_invoices,
    invoicesWithSkonto: response.invoices_with_skonto,
    skontoUsedCount: response.skonto_used_count,
    skontoMissedCount: response.skonto_missed_count,
    skontoPendingCount: response.skonto_pending_count,
    totalSavings: response.total_savings,
    missedSavings: response.missed_savings,
    potentialSavings: response.potential_savings,
    usageRate: response.usage_rate,
  };
}

/**
 * Holt monatliche Skonto-Zusammenfassung
 */
export async function getMonthlySkontoSummary(
  months: number = 12
): Promise<MonthlySkontoSummary[]> {
  const params = new URLSearchParams({
    months: months.toString(),
  });

  const response = await apiClient.get<Array<{
    year: string;
    month: string;
    used_amount: number;
    missed_amount: number;
    used_count: number;
    missed_count: number;
    usage_rate: number;
  }>>(`/invoices/skonto/monthly-summary?${params.toString()}`);

  return response.map((item) => ({
    year: item.year,
    month: item.month,
    usedAmount: item.used_amount,
    missedAmount: item.missed_amount,
    usedCount: item.used_count,
    missedCount: item.missed_count,
    usageRate: item.usage_rate,
  }));
}

// ==================== Export ====================

/**
 * Exportiert verpasste Skonto-Daten
 */
export async function exportMissedSkonto(
  format: 'xlsx' | 'csv' = 'xlsx',
  filter: Omit<MissedSkontoFilter, 'page' | 'perPage'> = {}
): Promise<Blob> {
  const params = new URLSearchParams({
    format,
  });

  if (filter.startDate) params.append('start_date', filter.startDate);
  if (filter.endDate) params.append('end_date', filter.endDate);

  const response = await fetch(
    `/api/v1/invoices/skonto/missed/export?${params.toString()}`,
    {
      credentials: 'include',
    }
  );

  if (!response.ok) {
    throw new Error('Export fehlgeschlagen');
  }

  return response.blob();
}

// ==================== Helper Functions ====================

/**
 * Transform Backend snake_case Response to Frontend camelCase
 */
function transformInvoiceResponse(data: InvoiceTrackingResponse): InvoiceTrackingResponse {
  return {
    id: data.id,
    documentId: data.document_id,
    invoiceNumber: data.invoice_number,
    invoiceDate: data.invoice_date,
    dueDate: data.due_date,
    amount: data.amount,
    currency: data.currency,
    status: data.status,
    paidAmount: data.paid_amount,
    paidAt: data.paid_at,
    dunningLevel: data.dunning_level,
    lastDunningAt: data.last_dunning_at,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
    isOverdue: data.is_overdue,
    daysOverdue: data.days_overdue,
  };
}
