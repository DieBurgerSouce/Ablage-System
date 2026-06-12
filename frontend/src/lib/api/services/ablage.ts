/**
 * Ablage API Service
 *
 * Kommuniziert mit den /api/v1/documents/category Endpoints
 * für kategorie-basierte Dokumentenverwaltung.
 *
 * Features:
 * - Kategorie-Dokumentenliste mit umfangreicher Filterung
 * - Bulk-Aktionen (ZIP, CSV, Delete, Tags)
 * - Zahlungsstatus-Verwaltung
 * - Aggregationen für Dashboard-Karten
 */

import { AxiosError } from 'axios';
import { apiClient } from '../client';
import type {
  CategoryDocumentFilter,
  CategoryDocumentResponse,
  CategoryDocumentListResponse,
  CategoryDocumentAggregations,
  BulkActionResult,
} from '@/features/ablage/types';

// ==================== Error Classes ====================

export class AblageApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(
    message: string,
    statusCode?: number,
    originalError?: unknown
  ) {
    super(message);
    this.name = 'AblageApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Backend Types ====================

interface CategoryDocumentBackend {
  id: string;
  filename: string;
  original_filename: string;
  document_type: string;
  processing_status: 'pending' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
  file_size: number;
  page_count: number;
  mime_type: string | null;
  created_at: string;
  updated_at: string;
  document_date: string | null;
  ocr_confidence: number | null;
  document_number: string | null;
  total_amount: number | null;
  currency: string;
  due_date: string | null;
  payment_status: 'offen' | 'bezahlt' | 'überfällig' | 'teilbezahlt';
  paid_amount: number | null;
  partner_name: string | null;
  tags: string[];
  thumbnail_url: string | null;
  preview_url: string | null;
  // Skonto-Daten (Backend CategoryDocumentResponse, app/db/schemas.py)
  skonto_percent: number | null;
  skonto_days: number | null;
  skonto_deadline: string | null;
  skonto_amount: number | null;
}

interface CategoryDocumentListBackend {
  items: CategoryDocumentBackend[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  filters_applied: Record<string, unknown>;
}

interface CategoryAggregationsBackend {
  total_documents: number;
  documents_by_status: Record<string, number>;
  documents_by_payment_status: Record<string, number>;
  total_amount: number;
  total_paid: number;
  total_open: number;
  total_overdue: number;
  currency: string;
  earliest_date: string | null;
  latest_date: string | null;
  overdue_count: number;
  overdue_documents: string[];
}

interface BulkOperationResultBackend {
  success: boolean;
  operation: string;
  success_count: number;
  failed_count: number;
  failed_ids: string[];
  errors: string[];
  message: string;
}

interface UpdatePaymentStatusResponseBackend {
  document_id: string;
  old_status: string;
  new_status: string;
  paid_amount: number | null;
  payment_date: string | null;
  message: string;
}

// ==================== Transformers ====================

function transformDocument(doc: CategoryDocumentBackend): CategoryDocumentResponse {
  return {
    id: doc.id,
    filename: doc.filename,
    originalFilename: doc.original_filename,
    documentType: doc.document_type,
    processingStatus: doc.processing_status,
    fileSize: doc.file_size,
    pageCount: doc.page_count,
    mimeType: doc.mime_type,
    createdAt: doc.created_at,
    updatedAt: doc.updated_at,
    documentDate: doc.document_date,
    ocrConfidence: doc.ocr_confidence,
    documentNumber: doc.document_number,
    totalAmount: doc.total_amount,
    currency: doc.currency,
    dueDate: doc.due_date,
    paymentStatus: doc.payment_status,
    paidAmount: doc.paid_amount,
    partnerName: doc.partner_name,
    tags: doc.tags,
    thumbnailUrl: doc.thumbnail_url,
    previewUrl: doc.preview_url,
    skontoPercent: doc.skonto_percent,
    skontoDays: doc.skonto_days,
    skontoDeadline: doc.skonto_deadline,
    skontoAmount: doc.skonto_amount,
  };
}

function transformListResponse(response: CategoryDocumentListBackend): CategoryDocumentListResponse {
  return {
    items: response.items.map(transformDocument),
    total: response.total,
    page: response.page,
    pageSize: response.page_size,
    totalPages: response.total_pages,
  };
}

function transformAggregations(agg: CategoryAggregationsBackend): CategoryDocumentAggregations {
  return {
    totalDocuments: agg.total_documents,
    documentsByStatus: agg.documents_by_status,
    documentsByPaymentStatus: agg.documents_by_payment_status,
    totalAmount: agg.total_amount,
    totalPaid: agg.total_paid,
    totalOpen: agg.total_open,
    totalOverdue: agg.total_overdue,
    currency: agg.currency,
    earliestDate: agg.earliest_date,
    latestDate: agg.latest_date,
    overdueCount: agg.overdue_count,
  };
}

function transformBulkResult(result: BulkOperationResultBackend): BulkActionResult {
  return {
    successCount: result.success_count,
    failedCount: result.failed_count,
    errors: result.errors.map((e, i) => ({
      documentId: result.failed_ids[i] || 'unknown',
      error: e,
    })),
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    // Spezielle Behandlung für 404
    if (statusCode === 404) {
      throw new AblageApiError(`${context}: Nicht gefunden`, 404, error);
    }

    // Spezielle Behandlung für 400
    if (statusCode === 400) {
      throw new AblageApiError(`${context}: ${message}`, 400, error);
    }

    // Generischer API-Fehler
    throw new AblageApiError(
      `${context}: ${message}`,
      statusCode,
      error
    );
  }

  // Unerwarteter Fehler
  throw new AblageApiError(
    `${context}: Unbekannter Fehler`,
    undefined,
    error
  );
}

// ==================== Query Parameter Builder ====================

interface CategoryDocumentsParams {
  business_entity_id: string;
  folder_id: string;
  category: string;
  entity_type: 'customer' | 'supplier';
  search?: string;
  date_from?: string;
  date_to?: string;
  amount_min?: number;
  amount_max?: number;
  processing_status?: string[];
  payment_status?: string[];
  tags?: string[];
  page: number;
  page_size: number;
  sort_by: string;
  sort_order: 'asc' | 'desc';
}

function buildQueryParams(filter: Partial<CategoryDocumentFilter>): CategoryDocumentsParams {
  return {
    business_entity_id: filter.businessEntityId || '',
    folder_id: filter.folderId || '',
    category: filter.category || '',
    entity_type: filter.entityType || 'customer',
    search: filter.search || undefined,
    date_from: filter.dateFrom || undefined,
    date_to: filter.dateTo || undefined,
    amount_min: filter.amountMin,
    amount_max: filter.amountMax,
    processing_status: filter.processingStatus?.length ? filter.processingStatus : undefined,
    payment_status: filter.paymentStatus?.length ? filter.paymentStatus : undefined,
    tags: filter.tags?.length ? filter.tags : undefined,
    page: filter.page ?? 0,
    page_size: filter.pageSize ?? 25,
    sort_by: filter.sortBy || 'document_date',
    sort_order: filter.sortOrder || 'desc',
  };
}

// ==================== Ablage Service ====================

export const ablageService = {
  // ==================== Kategorie-Dokumente ====================

  /**
   * Holt Dokumente für eine Kategorie mit Filterung und Pagination
   */
  getCategoryDocuments: async (
    filter: Partial<CategoryDocumentFilter>
  ): Promise<CategoryDocumentListResponse> => {
    try {
      const params = buildQueryParams(filter);

      const response = await apiClient.get<CategoryDocumentListBackend>(
        '/documents/category',
        { params }
      );

      return transformListResponse(response.data);
    } catch (error) {
      // Bei 404: Leere Liste zurückgeben
      if (error instanceof AxiosError && error.response?.status === 404) {
        return {
          items: [],
          total: 0,
          page: filter.page ?? 0,
          pageSize: filter.pageSize ?? 25,
          totalPages: 0,
        };
      }
      handleApiError(error, 'Dokumente laden');
    }
  },

  /**
   * Holt Aggregationen für eine Kategorie
   */
  getCategoryAggregations: async (
    filter: Pick<CategoryDocumentFilter, 'businessEntityId' | 'folderId' | 'category' | 'entityType'>
  ): Promise<CategoryDocumentAggregations> => {
    try {
      const response = await apiClient.get<CategoryAggregationsBackend>(
        '/documents/category/aggregations',
        {
          params: {
            business_entity_id: filter.businessEntityId,
            folder_id: filter.folderId,
            category: filter.category,
            entity_type: filter.entityType || 'customer',
          },
        }
      );

      return transformAggregations(response.data);
    } catch (error) {
      // Bei 404: Leere Aggregationen zurückgeben
      if (error instanceof AxiosError && error.response?.status === 404) {
        return {
          totalDocuments: 0,
          documentsByStatus: {},
          documentsByPaymentStatus: {},
          totalAmount: 0,
          totalPaid: 0,
          totalOpen: 0,
          totalOverdue: 0,
          currency: 'EUR',
          earliestDate: null,
          latestDate: null,
          overdueCount: 0,
        };
      }
      handleApiError(error, 'Aggregationen laden');
    }
  },

  /**
   * Holt ein einzelnes Dokument mit Details
   */
  getDocument: async (documentId: string): Promise<CategoryDocumentResponse> => {
    try {
      const response = await apiClient.get<CategoryDocumentBackend>(
        `/documents/${documentId}`
      );
      return transformDocument(response.data);
    } catch (error) {
      handleApiError(error, 'Dokument laden');
    }
  },

  // ==================== Bulk-Aktionen ====================

  /**
   * Laedt mehrere Dokumente als ZIP herunter
   */
  bulkDownloadZip: async (
    documentIds: string[],
    options?: { filename?: string }
  ): Promise<Blob> => {
    try {
      const response = await apiClient.post(
        '/documents/bulk/download-zip',
        {
          document_ids: documentIds,
          filename: options?.filename,
        },
        { responseType: 'blob' }
      );
      return response.data;
    } catch (error) {
      handleApiError(error, 'ZIP-Download');
    }
  },

  /**
   * Exportiert Dokument-Metadaten als CSV
   */
  bulkExportCsv: async (
    documentIds: string[],
    options?: {
      columns?: string[];
      includeAmounts?: boolean;
      includeDates?: boolean;
      delimiter?: string;
    }
  ): Promise<Blob> => {
    try {
      const response = await apiClient.post(
        '/documents/bulk/export-csv',
        {
          document_ids: documentIds,
          columns: options?.columns,
          include_amounts: options?.includeAmounts ?? true,
          include_dates: options?.includeDates ?? true,
          delimiter: options?.delimiter ?? ';',
        },
        { responseType: 'blob' }
      );
      return response.data;
    } catch (error) {
      handleApiError(error, 'CSV-Export');
    }
  },

  /**
   * Löscht mehrere Dokumente (Soft-Delete)
   */
  bulkDelete: async (
    documentIds: string[],
    options?: { reason?: string }
  ): Promise<BulkActionResult> => {
    try {
      const response = await apiClient.delete<BulkOperationResultBackend>(
        '/documents/bulk/delete',
        {
          data: {
            document_ids: documentIds,
            reason: options?.reason,
          },
        }
      );
      return transformBulkResult(response.data);
    } catch (error) {
      handleApiError(error, 'Dokumente löschen');
    }
  },

  /**
   * Verschiebt Dokumente in eine andere Kategorie
   */
  bulkMoveCategory: async (
    documentIds: string[],
    targetCategory: string
  ): Promise<BulkActionResult> => {
    try {
      const response = await apiClient.post<BulkOperationResultBackend>(
        '/documents/bulk/move-category',
        {
          document_ids: documentIds,
          target_category: targetCategory,
        }
      );
      return transformBulkResult(response.data);
    } catch (error) {
      handleApiError(error, 'Dokumente verschieben');
    }
  },

  /**
   * Setzt Tags für mehrere Dokumente
   */
  bulkSetTags: async (
    documentIds: string[],
    tags: string[],
    mode: 'add' | 'remove' | 'set' = 'add'
  ): Promise<BulkActionResult> => {
    try {
      const response = await apiClient.post<BulkOperationResultBackend>(
        '/documents/bulk/set-tags',
        {
          document_ids: documentIds,
          tags,
          mode,
        }
      );
      return transformBulkResult(response.data);
    } catch (error) {
      handleApiError(error, 'Tags setzen');
    }
  },

  // ==================== Zahlungsstatus ====================

  /**
   * Aktualisiert den Zahlungsstatus eines Dokuments
   */
  updatePaymentStatus: async (
    documentId: string,
    status: 'offen' | 'bezahlt' | 'überfällig' | 'teilbezahlt',
    paidAmount?: number
  ): Promise<{ oldStatus: string; newStatus: string; message: string }> => {
    try {
      const response = await apiClient.patch<UpdatePaymentStatusResponseBackend>(
        `/documents/${documentId}/payment-status`,
        {
          status,
          paid_amount: paidAmount,
        }
      );

      return {
        oldStatus: response.data.old_status,
        newStatus: response.data.new_status,
        message: response.data.message,
      };
    } catch (error) {
      handleApiError(error, 'Zahlungsstatus aktualisieren');
    }
  },

  /**
   * Markiert mehrere Dokumente als bezahlt
   */
  bulkMarkAsPaid: async (
    documentIds: string[],
    paymentDate?: string
  ): Promise<BulkActionResult> => {
    try {
      const response = await apiClient.post<BulkOperationResultBackend>(
        '/documents/bulk/mark-as-paid',
        {
          document_ids: documentIds,
          payment_date: paymentDate || new Date().toISOString(),
        }
      );
      return transformBulkResult(response.data);
    } catch (error) {
      handleApiError(error, 'Als bezahlt markieren');
    }
  },

  // ==================== Helper ====================

  /**
   * Erstellt Download-Link für Blob und triggert Download
   */
  downloadBlob: (blob: Blob, filename: string): void => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },
};
