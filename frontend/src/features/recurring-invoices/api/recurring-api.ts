/**
 * Recurring Invoice API Service
 *
 * Kommuniziert mit den /api/v1/recurring-invoices Endpoints
 * fuer Abo-Rechnungsverwaltung und -erkennung.
 *
 * Features:
 * - CRUD fuer wiederkehrende Rechnungen
 * - Muster-Erkennung
 * - Fehlende Rechnungen
 * - Preisaenderungen
 * - Soll/Ist-Berichte
 * - Manuelle Dokumentzuordnung
 */

import { apiClient } from '@/lib/api/client';
import type {
  RecurringInvoiceListResponse,
  RecurringInvoiceDetailResponse,
  RecurringInvoiceResponse,
  RecurringInvoiceCreate,
  RecurringInvoiceUpdate,
  RecurringInvoiceFilter,
  DetectedPatternResponse,
  DetectPatternsParams,
  MissingInvoiceResponse,
  PriceChangeResponse,
  SollIstReportResponse,
  OccurrenceResponse,
} from '../types/recurring-types';

// ==================== List / Detail ====================

/**
 * Listet wiederkehrende Rechnungen mit Filter und Pagination
 */
export async function fetchRecurringInvoices(
  params: RecurringInvoiceFilter = {}
): Promise<RecurringInvoiceListResponse> {
  const queryParams: Record<string, string | number> = {};

  if (params.status) {
    queryParams.status = params.status;
  }
  if (params.page !== undefined) {
    queryParams.page = params.page;
  }
  if (params.page_size !== undefined) {
    queryParams.page_size = params.page_size;
  }

  const response = await apiClient.get<RecurringInvoiceListResponse>(
    '/recurring-invoices',
    { params: queryParams }
  );

  return response.data;
}

/**
 * Ruft eine einzelne Abo-Rechnung mit Occurrences ab
 */
export async function fetchRecurringInvoice(
  id: string
): Promise<RecurringInvoiceDetailResponse> {
  const response = await apiClient.get<RecurringInvoiceDetailResponse>(
    `/recurring-invoices/${id}`
  );

  return response.data;
}

// ==================== Create / Update ====================

/**
 * Erstellt eine neue Abo-Rechnung manuell
 */
export async function createRecurringInvoice(
  data: RecurringInvoiceCreate
): Promise<RecurringInvoiceResponse> {
  const response = await apiClient.post<RecurringInvoiceResponse>(
    '/recurring-invoices',
    data
  );

  return response.data;
}

/**
 * Aktualisiert eine Abo-Rechnung
 */
export async function updateRecurringInvoice(
  id: string,
  data: RecurringInvoiceUpdate
): Promise<RecurringInvoiceResponse> {
  const response = await apiClient.patch<RecurringInvoiceResponse>(
    `/recurring-invoices/${id}`,
    data
  );

  return response.data;
}

// ==================== Detection ====================

/**
 * Erkennt wiederkehrende Rechnungsmuster
 */
export async function detectPatterns(
  params?: DetectPatternsParams
): Promise<DetectedPatternResponse[]> {
  const queryParams: Record<string, number> = {};

  if (params?.min_occurrences !== undefined) {
    queryParams.min_occurrences = params.min_occurrences;
  }
  if (params?.lookback_months !== undefined) {
    queryParams.lookback_months = params.lookback_months;
  }

  const response = await apiClient.post<DetectedPatternResponse[]>(
    '/recurring-invoices/detect',
    null,
    { params: queryParams }
  );

  return response.data;
}

// ==================== Alerts ====================

/**
 * Ruft fehlende Rechnungen ab
 */
export async function fetchMissingInvoices(): Promise<MissingInvoiceResponse[]> {
  const response = await apiClient.get<MissingInvoiceResponse[]>(
    '/recurring-invoices/missing'
  );

  return response.data;
}

/**
 * Ruft Preisaenderungen ab
 */
export async function fetchPriceChanges(): Promise<PriceChangeResponse[]> {
  const response = await apiClient.get<PriceChangeResponse[]>(
    '/recurring-invoices/price-changes'
  );

  return response.data;
}

// ==================== Reports ====================

/**
 * Ruft den Soll/Ist-Bericht ab
 */
export async function fetchSollIstReport(
  year: number,
  month: number
): Promise<SollIstReportResponse> {
  const response = await apiClient.get<SollIstReportResponse>(
    '/recurring-invoices/soll-ist',
    { params: { year, month } }
  );

  return response.data;
}

// ==================== Manual Matching ====================

/**
 * Ordnet ein Dokument manuell einer Abo-Rechnung zu
 */
export async function manualMatchDocument(
  recurringId: string,
  documentId: string
): Promise<OccurrenceResponse> {
  const response = await apiClient.post<OccurrenceResponse>(
    `/recurring-invoices/${recurringId}/match`,
    { document_id: documentId }
  );

  return response.data;
}
