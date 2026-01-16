/**
 * Invoice Tracking API Service
 *
 * Kommuniziert mit den /api/v1/invoices Endpoints
 * für Rechnungsverfolgung und Mahnwesen.
 *
 * Features:
 * - CRUD für InvoiceTracking
 * - Als bezahlt markieren
 * - Mahnstufe erhöhen
 * - Statistiken abrufen
 */

import { AxiosError } from 'axios';
import { apiClient } from '@/lib/api/client';
import type {
  InvoiceTrackingResponse,
  InvoiceTrackingBackend,
  InvoiceStatisticsResponse,
  InvoiceStatisticsBackend,
  InvoiceFilter,
  InvoiceTrackingCreate,
  InvoiceTrackingUpdate,
  DunningLevel,
  InvoiceStatus,
} from '../types/invoice-types';

// ==================== Error Classes ====================

export class InvoiceApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(
    message: string,
    statusCode?: number,
    originalError?: unknown
  ) {
    super(message);
    this.name = 'InvoiceApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Transformers ====================

function transformInvoice(inv: InvoiceTrackingBackend): InvoiceTrackingResponse {
  return {
    id: inv.id,
    documentId: inv.document_id,
    invoiceNumber: inv.invoice_number,
    invoiceDate: inv.invoice_date,
    dueDate: inv.due_date,
    amount: inv.amount,
    currency: inv.currency,
    status: inv.status,
    dunningLevel: inv.dunning_level as DunningLevel,
    paidAt: inv.paid_at,
    paidAmount: inv.paid_amount,
    lastDunningAt: inv.last_dunning_at,
    notes: inv.notes,
    createdAt: inv.created_at,
    updatedAt: inv.updated_at,
    isOverdue: inv.is_overdue ?? false,
    daysOverdue: inv.days_overdue ?? 0,
  };
}

function transformStatistics(stats: InvoiceStatisticsBackend): InvoiceStatisticsResponse {
  return {
    totalInvoices: stats.totalInvoices,
    totalAmount: stats.totalAmount,
    statusDistribution: stats.statusDistribution,
    overdueInvoices: stats.overdueInvoices,
    generatedAt: stats.generatedAt,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new InvoiceApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 409) {
      throw new InvoiceApiError(`${context}: ${message}`, 409, error);
    }

    if (statusCode === 400) {
      throw new InvoiceApiError(`${context}: ${message}`, 400, error);
    }

    throw new InvoiceApiError(
      `${context}: ${message}`,
      statusCode,
      error
    );
  }

  throw new InvoiceApiError(
    `${context}: Unbekannter Fehler`,
    undefined,
    error
  );
}

// ==================== Invoice Service ====================

export const invoiceService = {
  // ==================== List / Search ====================

  /**
   * Listet Rechnungen mit Filter und Pagination
   */
  listInvoices: async (
    filter: Partial<InvoiceFilter> = {}
  ): Promise<InvoiceTrackingResponse[]> => {
    try {
      const params: Record<string, string | number | boolean> = {
        page: filter.page ?? 1,
        per_page: filter.perPage ?? 20,
      };

      if (filter.status) {
        params.status = filter.status;
      }
      if (filter.overdueOnly) {
        params.overdue_only = filter.overdueOnly;
      }
      if (filter.documentId) {
        params.document_id = filter.documentId;
      }

      const response = await apiClient.get<InvoiceTrackingBackend[]>(
        '/invoices',
        { params }
      );

      return response.data.map(transformInvoice);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Rechnungen laden');
    }
  },

  // ==================== Statistics ====================

  /**
   * Ruft aggregierte Statistiken ab
   */
  getStatistics: async (): Promise<InvoiceStatisticsResponse> => {
    try {
      const response = await apiClient.get<InvoiceStatisticsBackend>(
        '/invoices/statistics/summary'
      );

      return transformStatistics(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return {
          totalInvoices: 0,
          totalAmount: 0,
          statusDistribution: {},
          overdueInvoices: { count: 0, amount: 0 },
          generatedAt: new Date().toISOString(),
        };
      }
      handleApiError(error, 'Statistiken laden');
    }
  },

  // ==================== Get Single ====================

  /**
   * Ruft eine einzelne Rechnung ab
   */
  getInvoice: async (invoiceId: string): Promise<InvoiceTrackingResponse> => {
    try {
      const response = await apiClient.get<InvoiceTrackingBackend>(
        `/invoices/${invoiceId}`
      );

      return transformInvoice(response.data);
    } catch (error) {
      handleApiError(error, 'Rechnung laden');
    }
  },

  // ==================== Create ====================

  /**
   * Erstellt eine neue Rechnungsverfolgung
   */
  createInvoice: async (
    data: InvoiceTrackingCreate
  ): Promise<InvoiceTrackingResponse> => {
    try {
      const response = await apiClient.post<InvoiceTrackingBackend>(
        '/invoices',
        {
          document_id: data.documentId,
          invoice_number: data.invoiceNumber,
          invoice_date: data.invoiceDate,
          due_date: data.dueDate,
          amount: data.amount,
          currency: data.currency ?? 'EUR',
          status: data.status ?? 'open',
        }
      );

      return transformInvoice(response.data);
    } catch (error) {
      handleApiError(error, 'Rechnungsverfolgung erstellen');
    }
  },

  // ==================== Update ====================

  /**
   * Aktualisiert eine Rechnungsverfolgung
   */
  updateInvoice: async (
    invoiceId: string,
    data: InvoiceTrackingUpdate
  ): Promise<InvoiceTrackingResponse> => {
    try {
      const payload: Record<string, unknown> = {};

      if (data.invoiceNumber !== undefined) payload.invoice_number = data.invoiceNumber;
      if (data.invoiceDate !== undefined) payload.invoice_date = data.invoiceDate;
      if (data.dueDate !== undefined) payload.due_date = data.dueDate;
      if (data.amount !== undefined) payload.amount = data.amount;
      if (data.currency !== undefined) payload.currency = data.currency;
      if (data.status !== undefined) payload.status = data.status;
      if (data.paidAt !== undefined) payload.paid_at = data.paidAt;
      if (data.paidAmount !== undefined) payload.paid_amount = data.paidAmount;
      if (data.notes !== undefined) payload.notes = data.notes;

      const response = await apiClient.patch<InvoiceTrackingBackend>(
        `/invoices/${invoiceId}`,
        payload
      );

      return transformInvoice(response.data);
    } catch (error) {
      handleApiError(error, 'Rechnungsverfolgung aktualisieren');
    }
  },

  // ==================== Mark Paid ====================

  /**
   * Markiert eine Rechnung als bezahlt
   */
  markPaid: async (
    invoiceId: string,
    options?: { paidAmount?: number; paidAt?: string }
  ): Promise<InvoiceTrackingResponse> => {
    try {
      const params: Record<string, string | number> = {};

      if (options?.paidAmount !== undefined) {
        params.paid_amount = options.paidAmount;
      }
      if (options?.paidAt) {
        params.paid_at = options.paidAt;
      }

      const response = await apiClient.post<InvoiceTrackingBackend>(
        `/invoices/${invoiceId}/mark-paid`,
        null,
        { params }
      );

      return transformInvoice(response.data);
    } catch (error) {
      handleApiError(error, 'Als bezahlt markieren');
    }
  },

  // ==================== Increase Dunning ====================

  /**
   * Erhöht die Mahnstufe einer Rechnung
   */
  increaseDunning: async (
    invoiceId: string
  ): Promise<InvoiceTrackingResponse> => {
    try {
      const response = await apiClient.post<InvoiceTrackingBackend>(
        `/invoices/${invoiceId}/increase-dunning`
      );

      return transformInvoice(response.data);
    } catch (error) {
      handleApiError(error, 'Mahnstufe erhöhen');
    }
  },

  // ==================== Delete ====================

  /**
   * Löscht eine Rechnungsverfolgung (Soft-Delete)
   */
  deleteInvoice: async (invoiceId: string): Promise<void> => {
    try {
      await apiClient.delete(`/invoices/${invoiceId}`);
    } catch (error) {
      handleApiError(error, 'Rechnungsverfolgung löschen');
    }
  },
};

// ==================== Computed Helpers ====================

/**
 * Berechnet aggregierte KPI-Werte aus Statistiken
 */
export function computeKPIs(stats: InvoiceStatisticsResponse): {
  openAmount: number;
  overdueAmount: number;
  activeDunnings: number;
  paidAmount: number;
} {
  let openAmount = 0;
  let paidAmount = 0;
  let activeDunnings = 0;

  for (const [status, data] of Object.entries(stats.statusDistribution)) {
    if (status === 'paid') {
      paidAmount += data.amount;
    } else if (status === 'cancelled') {
      // Ignore cancelled
    } else {
      openAmount += data.amount;
    }

    if (status === 'dunning') {
      activeDunnings = data.count;
    }
  }

  return {
    openAmount,
    overdueAmount: stats.overdueInvoices.amount,
    activeDunnings,
    paidAmount,
  };
}
