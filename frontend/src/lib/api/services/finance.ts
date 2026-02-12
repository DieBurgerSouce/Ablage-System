/**
 * Finance API Service
 *
 * Kommuniziert mit den /api/v1/finance Endpoints
 * für Jahr-basierte Finanz-Dokumentenverwaltung.
 *
 * Features:
 * - Finanz-Jahre mit Dokument-Counts
 * - Aggregationen (Nachzahlung/Erstattung, Fristen)
 * - Kategorie-Dokumentenliste (18 Kategorien in 4 Paketen)
 */

import { AxiosError } from 'axios';
import { apiClient } from '../client';
import type {
  FinanceYear,
  FinanceAggregations,
  FinanceDocumentCategory,
  FinancePackageType,
  TaxType,
} from '@/features/finanzen/types';

// ==================== Error Classes ====================

export class FinanceApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(
    message: string,
    statusCode?: number,
    originalError?: unknown
  ) {
    super(message);
    this.name = 'FinanceApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Backend Types ====================

interface FinanceYearBackend {
  id: string;
  year: number;
  is_active: boolean;
  last_document_date: string | null;
  document_counts: Record<string, number>;
  total_documents: number;
  total_nachzahlung: number;
  total_erstattung: number;
  pending_deadlines: number;
}

interface FinanceYearListBackend {
  items: FinanceYearBackend[];
  total: number;
}

interface FinanceAggregationsBackend {
  total_documents: number;
  total_nachzahlung: number;
  total_erstattung: number;
  saldo: number;
  pending_deadlines: number;
  overdue_deadlines: number;
  documents_by_category: Record<string, number>;
  documents_by_package: Record<string, number>;
}

interface FinanceCategoryDocumentBackend {
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
  // Finance-specific fields
  einspruchsfrist: string | null;
  aktenzeichen: string | null;
  steuernummer: string | null;
  finanzamt: string | null;
  steuerart: TaxType | null;
  zeitraum: string | null;
  nachzahlung: number | null;
  erstattung: number | null;
  versicherungsnummer: string | null;
  vertragsnummer: string | null;
  tags: string[];
  thumbnail_url: string | null;
  preview_url: string | null;
  // Anomaly fields (Enterprise Feature)
  has_anomalies: boolean;
  anomaly_count: number;
  risk_score: number | null;
}

interface FinanceCategoryDocumentListBackend {
  items: FinanceCategoryDocumentBackend[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface FinanceCategoryAggregationsBackend {
  category: string;
  year: number;
  total_documents: number;
  total_nachzahlung: number;
  total_erstattung: number;
  pending_deadlines: number;
  overdue_deadlines: number;
  earliest_date: string | null;
  latest_date: string | null;
}

// CRUD Backend Types
interface FinanceDocumentUploadResultBackend {
  id: string;
  filename: string;
  original_filename: string;
  category: string;
  year: number;
  document_type: string;
  processing_status: string;
  file_size: number;
  storage_path: string;
  ocr_job_id: string | null;
  message: string;
  created_at: string;
}

interface FinanceDocumentDeleteResultBackend {
  id: string;
  deleted: boolean;
  deleted_at: string;
  message: string;
}

// ==================== Frontend Types ====================

export interface FinanceCategoryDocument {
  id: string;
  filename: string;
  originalFilename: string;
  documentType: string;
  processingStatus: 'pending' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
  fileSize: number;
  pageCount: number;
  mimeType: string | null;
  createdAt: string;
  updatedAt: string;
  documentDate: string | null;
  ocrConfidence: number | null;
  documentNumber: string | null;
  totalAmount: number | null;
  currency: string;
  // Finance-specific fields
  einspruchsfrist: string | null;
  aktenzeichen: string | null;
  steuernummer: string | null;
  finanzamt: string | null;
  steuerart: TaxType | null;
  zeitraum: string | null;
  nachzahlung: number | null;
  erstattung: number | null;
  versicherungsnummer: string | null;
  vertragsnummer: string | null;
  tags: string[];
  thumbnailUrl: string | null;
  previewUrl: string | null;
  // Anomaly fields (Enterprise Feature)
  hasAnomalies: boolean;
  anomalyCount: number;
  riskScore: number | null;
}

export interface FinanceCategoryDocumentList {
  items: FinanceCategoryDocument[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface FinanceCategoryAggregations {
  category: string;
  year: number;
  totalDocuments: number;
  totalNachzahlung: number;
  totalErstattung: number;
  pendingDeadlines: number;
  overdueDeadlines: number;
  earliestDate: string | null;
  latestDate: string | null;
}

export interface FinanceCategoryFilter {
  year: string;
  category: string;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  amountMin?: number;
  amountMax?: number;
  steuerart?: string;
  page: number;
  pageSize: number;
  sortBy: string;
  sortOrder: 'asc' | 'desc';
}

// CRUD Frontend Types
export interface FinanceDocumentUploadMetadata {
  documentDate?: string;
  totalAmount?: number;
  nachzahlung?: number;
  erstattung?: number;
  einspruchsfrist?: string;
  aktenzeichen?: string;
  steuernummer?: string;
  finanzamt?: string;
  steuerart?: string;
  zeitraum?: string;
  versicherungsnummer?: string;
  vertragsnummer?: string;
  skipOcr?: boolean;
}

export interface FinanceDocumentUploadResult {
  id: string;
  filename: string;
  originalFilename: string;
  category: string;
  year: number;
  documentType: string;
  processingStatus: string;
  fileSize: number;
  storagePath: string;
  ocrJobId: string | null;
  message: string;
  createdAt: string;
}

export interface FinanceDocumentUpdateData {
  category?: string;
  documentDate?: string;
  totalAmount?: number;
  nachzahlung?: number;
  erstattung?: number;
  einspruchsfrist?: string;
  aktenzeichen?: string;
  steuernummer?: string;
  finanzamt?: string;
  steuerart?: string;
  zeitraum?: string;
  versicherungsnummer?: string;
  vertragsnummer?: string;
}

export interface FinanceDocumentDeleteResult {
  id: string;
  deleted: boolean;
  deletedAt: string;
  message: string;
}

// ==================== Bulk Operation Types ====================

export interface FinanceBulkDeleteResult {
  deletedCount: number;
  failedCount: number;
  deletedIds: string[];
  failedIds: string[];
  errors: string[];
  message: string;
}

export interface FinanceBulkUpdateData {
  category?: string;
  year?: number;
  steuerart?: string;
}

export interface FinanceBulkUpdateResult {
  updatedCount: number;
  failedCount: number;
  updatedIds: string[];
  failedIds: string[];
  errors: string[];
  message: string;
}

export type FinanceExportFormat = 'json' | 'csv' | 'zip';

export interface FinanceExportOptions {
  documentIds?: string[];
  year?: number;
  category?: string;
  format?: FinanceExportFormat;
  includeFiles?: boolean;
}

export interface FinanceExportResult {
  exportId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  downloadUrl: string | null;
  documentCount: number;
  fileSizeBytes: number | null;
  expiresAt: string | null;
  message: string;
}

// ==================== Transformers ====================

function transformYear(year: FinanceYearBackend): FinanceYear {
  return {
    id: year.id,
    year: year.year,
    isActive: year.is_active,
    lastDocumentDate: year.last_document_date || '',
    documentCounts: year.document_counts as Record<FinanceDocumentCategory, number>,
    totalDocuments: year.total_documents,
    totalNachzahlung: year.total_nachzahlung,
    totalErstattung: year.total_erstattung,
    pendingDeadlines: year.pending_deadlines,
  };
}

function transformYears(response: FinanceYearListBackend): FinanceYear[] {
  return response.items.map(transformYear);
}

function transformAggregations(agg: FinanceAggregationsBackend): FinanceAggregations {
  return {
    totalDocuments: agg.total_documents,
    totalNachzahlung: agg.total_nachzahlung,
    totalErstattung: agg.total_erstattung,
    saldo: agg.saldo,
    pendingDeadlines: agg.pending_deadlines,
    documentsByPackage: agg.documents_by_package as Record<FinancePackageType, number>,
  };
}

function transformDocument(doc: FinanceCategoryDocumentBackend): FinanceCategoryDocument {
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
    // Finance-specific
    einspruchsfrist: doc.einspruchsfrist,
    aktenzeichen: doc.aktenzeichen,
    steuernummer: doc.steuernummer,
    finanzamt: doc.finanzamt,
    steuerart: doc.steuerart,
    zeitraum: doc.zeitraum,
    nachzahlung: doc.nachzahlung,
    erstattung: doc.erstattung,
    versicherungsnummer: doc.versicherungsnummer,
    vertragsnummer: doc.vertragsnummer,
    tags: doc.tags,
    thumbnailUrl: doc.thumbnail_url,
    previewUrl: doc.preview_url,
    // Anomaly fields
    hasAnomalies: doc.has_anomalies ?? false,
    anomalyCount: doc.anomaly_count ?? 0,
    riskScore: doc.risk_score ?? null,
  };
}

function transformDocumentList(response: FinanceCategoryDocumentListBackend): FinanceCategoryDocumentList {
  return {
    items: response.items.map(transformDocument),
    total: response.total,
    page: response.page,
    pageSize: response.page_size,
    totalPages: response.total_pages,
  };
}

function transformCategoryAggregations(agg: FinanceCategoryAggregationsBackend): FinanceCategoryAggregations {
  return {
    category: agg.category,
    year: agg.year,
    totalDocuments: agg.total_documents,
    totalNachzahlung: agg.total_nachzahlung,
    totalErstattung: agg.total_erstattung,
    pendingDeadlines: agg.pending_deadlines,
    overdueDeadlines: agg.overdue_deadlines,
    earliestDate: agg.earliest_date,
    latestDate: agg.latest_date,
  };
}

function transformUploadResult(result: FinanceDocumentUploadResultBackend): FinanceDocumentUploadResult {
  return {
    id: result.id,
    filename: result.filename,
    originalFilename: result.original_filename,
    category: result.category,
    year: result.year,
    documentType: result.document_type,
    processingStatus: result.processing_status,
    fileSize: result.file_size,
    storagePath: result.storage_path,
    ocrJobId: result.ocr_job_id,
    message: result.message,
    createdAt: result.created_at,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new FinanceApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 400) {
      throw new FinanceApiError(`${context}: ${message}`, 400, error);
    }

    throw new FinanceApiError(
      `${context}: ${message}`,
      statusCode,
      error
    );
  }

  throw new FinanceApiError(
    `${context}: Unbekannter Fehler`,
    undefined,
    error
  );
}

// ==================== Query Parameter Builder ====================

interface CategoryDocumentsParams {
  search?: string;
  date_from?: string;
  date_to?: string;
  amount_min?: number;
  amount_max?: number;
  steuerart?: string;
  page: number;
  page_size: number;
  sort_by: string;
  sort_order: 'asc' | 'desc';
}

function buildCategoryParams(filter: Partial<FinanceCategoryFilter>): CategoryDocumentsParams {
  return {
    search: filter.search || undefined,
    date_from: filter.dateFrom || undefined,
    date_to: filter.dateTo || undefined,
    amount_min: filter.amountMin,
    amount_max: filter.amountMax,
    steuerart: filter.steuerart || undefined,
    page: filter.page ?? 0,
    page_size: filter.pageSize ?? 25,
    sort_by: filter.sortBy || 'document_date',
    sort_order: filter.sortOrder || 'desc',
  };
}

// ==================== Finance Service ====================

export const financeService = {
  // ==================== Jahre ====================

  /**
   * Holt alle Finanz-Jahre mit Dokument-Counts
   */
  getYears: async (): Promise<FinanceYear[]> => {
    try {
      const response = await apiClient.get<FinanceYearListBackend>('/finance/years');
      return transformYears(response.data);
    } catch (error) {
      // Bei 404: Leere Liste zurückgeben
      if (error instanceof AxiosError && error.response?.status === 404) {
        return [];
      }
      handleApiError(error, 'Finanz-Jahre laden');
    }
  },

  /**
   * Holt Details für ein spezifisches Jahr
   */
  getYear: async (year: string): Promise<FinanceYear | null> => {
    try {
      const response = await apiClient.get<FinanceYearBackend>(`/finance/years/${year}`);
      return transformYear(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return null;
      }
      handleApiError(error, 'Finanz-Jahr laden');
    }
  },

  // ==================== Aggregationen ====================

  /**
   * Holt Gesamt-Aggregationen über alle Jahre
   */
  getOverallAggregations: async (): Promise<FinanceAggregations> => {
    try {
      const response = await apiClient.get<FinanceAggregationsBackend>('/finance/aggregations');
      return transformAggregations(response.data);
    } catch (error) {
      // Bei Fehler: Default-Aggregationen zurückgeben
      if (error instanceof AxiosError && error.response?.status === 404) {
        return {
          totalDocuments: 0,
          totalNachzahlung: 0,
          totalErstattung: 0,
          saldo: 0,
          pendingDeadlines: 0,
          documentsByPackage: {
            steuern: 0,
            personal: 0,
            versicherung: 0,
            bank: 0,
          },
        };
      }
      handleApiError(error, 'Gesamt-Aggregationen laden');
    }
  },

  /**
   * Holt Aggregationen für ein Jahr
   */
  getYearAggregations: async (year: string): Promise<FinanceAggregations> => {
    try {
      const response = await apiClient.get<FinanceAggregationsBackend>(
        `/finance/years/${year}/aggregations`
      );
      return transformAggregations(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return {
          totalDocuments: 0,
          totalNachzahlung: 0,
          totalErstattung: 0,
          saldo: 0,
          pendingDeadlines: 0,
          documentsByPackage: {
            steuern: 0,
            personal: 0,
            versicherung: 0,
            bank: 0,
          },
        };
      }
      handleApiError(error, 'Jahr-Aggregationen laden');
    }
  },

  // ==================== Kategorie-Dokumente ====================

  /**
   * Holt Dokumente für eine Finanz-Kategorie
   */
  getCategoryDocuments: async (
    year: string,
    category: string,
    filter: Partial<FinanceCategoryFilter> = {}
  ): Promise<FinanceCategoryDocumentList> => {
    try {
      const params = buildCategoryParams(filter);
      const response = await apiClient.get<FinanceCategoryDocumentListBackend>(
        `/finance/years/${year}/categories/${category}/documents`,
        { params }
      );
      return transformDocumentList(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return {
          items: [],
          total: 0,
          page: filter.page ?? 0,
          pageSize: filter.pageSize ?? 25,
          totalPages: 0,
        };
      }
      handleApiError(error, 'Kategorie-Dokumente laden');
    }
  },

  /**
   * Holt Aggregationen für eine Kategorie
   */
  getCategoryAggregations: async (
    year: string,
    category: string
  ): Promise<FinanceCategoryAggregations> => {
    try {
      const response = await apiClient.get<FinanceCategoryAggregationsBackend>(
        `/finance/years/${year}/categories/${category}/aggregations`
      );
      return transformCategoryAggregations(response.data);
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return {
          category,
          year: parseInt(year, 10),
          totalDocuments: 0,
          totalNachzahlung: 0,
          totalErstattung: 0,
          pendingDeadlines: 0,
          overdueDeadlines: 0,
          earliestDate: null,
          latestDate: null,
        };
      }
      handleApiError(error, 'Kategorie-Aggregationen laden');
    }
  },

  // ==================== Einzelnes Dokument ====================

  /**
   * Holt ein einzelnes Finanz-Dokument
   */
  getDocument: async (documentId: string): Promise<FinanceCategoryDocument> => {
    try {
      const response = await apiClient.get<FinanceCategoryDocumentBackend>(
        `/finance/documents/${documentId}`
      );
      return transformDocument(response.data);
    } catch (error) {
      handleApiError(error, 'Finanz-Dokument laden');
    }
  },

  // ==================== CRUD Operationen ====================

  /**
   * Lädt ein neues Finanz-Dokument hoch
   */
  uploadDocument: async (
    year: string,
    category: string,
    file: File,
    metadata?: FinanceDocumentUploadMetadata
  ): Promise<FinanceDocumentUploadResult> => {
    try {
      const formData = new FormData();
      formData.append('file', file);

      if (metadata) {
        if (metadata.documentDate) formData.append('document_date', metadata.documentDate);
        if (metadata.totalAmount !== undefined) formData.append('total_amount', String(metadata.totalAmount));
        if (metadata.nachzahlung !== undefined) formData.append('nachzahlung', String(metadata.nachzahlung));
        if (metadata.erstattung !== undefined) formData.append('erstattung', String(metadata.erstattung));
        if (metadata.einspruchsfrist) formData.append('einspruchsfrist', metadata.einspruchsfrist);
        if (metadata.aktenzeichen) formData.append('aktenzeichen', metadata.aktenzeichen);
        if (metadata.steuernummer) formData.append('steuernummer', metadata.steuernummer);
        if (metadata.finanzamt) formData.append('finanzamt', metadata.finanzamt);
        if (metadata.steuerart) formData.append('steuerart', metadata.steuerart);
        if (metadata.zeitraum) formData.append('zeitraum', metadata.zeitraum);
        if (metadata.versicherungsnummer) formData.append('versicherungsnummer', metadata.versicherungsnummer);
        if (metadata.vertragsnummer) formData.append('vertragsnummer', metadata.vertragsnummer);
        if (metadata.skipOcr !== undefined) formData.append('skip_ocr', String(metadata.skipOcr));
      }

      const response = await apiClient.post<FinanceDocumentUploadResultBackend>(
        `/finance/years/${year}/categories/${category}/documents`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );

      return transformUploadResult(response.data);
    } catch (error) {
      handleApiError(error, 'Dokument hochladen');
    }
  },

  /**
   * Aktualisiert ein Finanz-Dokument
   */
  updateDocument: async (
    documentId: string,
    updateData: FinanceDocumentUpdateData
  ): Promise<FinanceCategoryDocument> => {
    try {
      const backendData: Record<string, unknown> = {};

      if (updateData.category !== undefined) backendData.category = updateData.category;
      if (updateData.documentDate !== undefined) backendData.document_date = updateData.documentDate;
      if (updateData.totalAmount !== undefined) backendData.total_amount = updateData.totalAmount;
      if (updateData.nachzahlung !== undefined) backendData.nachzahlung = updateData.nachzahlung;
      if (updateData.erstattung !== undefined) backendData.erstattung = updateData.erstattung;
      if (updateData.einspruchsfrist !== undefined) backendData.einspruchsfrist = updateData.einspruchsfrist;
      if (updateData.aktenzeichen !== undefined) backendData.aktenzeichen = updateData.aktenzeichen;
      if (updateData.steuernummer !== undefined) backendData.steuernummer = updateData.steuernummer;
      if (updateData.finanzamt !== undefined) backendData.finanzamt = updateData.finanzamt;
      if (updateData.steuerart !== undefined) backendData.steuerart = updateData.steuerart;
      if (updateData.zeitraum !== undefined) backendData.zeitraum = updateData.zeitraum;
      if (updateData.versicherungsnummer !== undefined) backendData.versicherungsnummer = updateData.versicherungsnummer;
      if (updateData.vertragsnummer !== undefined) backendData.vertragsnummer = updateData.vertragsnummer;

      const response = await apiClient.patch<FinanceCategoryDocumentBackend>(
        `/finance/documents/${documentId}`,
        backendData
      );

      return transformDocument(response.data);
    } catch (error) {
      handleApiError(error, 'Dokument aktualisieren');
    }
  },

  /**
   * Löscht ein Finanz-Dokument (Soft-Delete)
   */
  deleteDocument: async (documentId: string): Promise<FinanceDocumentDeleteResult> => {
    try {
      const response = await apiClient.delete<FinanceDocumentDeleteResultBackend>(
        `/finance/documents/${documentId}`
      );

      return {
        id: response.data.id,
        deleted: response.data.deleted,
        deletedAt: response.data.deleted_at,
        message: response.data.message,
      };
    } catch (error) {
      handleApiError(error, 'Dokument löschen');
    }
  },

  // ==================== Bulk Operationen ====================

  /**
   * Löscht mehrere Dokumente auf einmal
   */
  bulkDeleteDocuments: async (documentIds: string[]): Promise<FinanceBulkDeleteResult> => {
    try {
      const response = await apiClient.post<{
        deleted_count: number;
        failed_count: number;
        deleted_ids: string[];
        failed_ids: string[];
        errors: string[];
        message: string;
      }>('/finance/documents/bulk-delete', {
        document_ids: documentIds,
      });

      return {
        deletedCount: response.data.deleted_count,
        failedCount: response.data.failed_count,
        deletedIds: response.data.deleted_ids,
        failedIds: response.data.failed_ids,
        errors: response.data.errors,
        message: response.data.message,
      };
    } catch (error) {
      handleApiError(error, 'Bulk-Löschung');
    }
  },

  /**
   * Aktualisiert mehrere Dokumente auf einmal
   */
  bulkUpdateDocuments: async (
    documentIds: string[],
    updateData: FinanceBulkUpdateData
  ): Promise<FinanceBulkUpdateResult> => {
    try {
      const response = await apiClient.patch<{
        updated_count: number;
        failed_count: number;
        updated_ids: string[];
        failed_ids: string[];
        errors: string[];
        message: string;
      }>('/finance/documents/bulk-update', {
        document_ids: documentIds,
        ...updateData,
      });

      return {
        updatedCount: response.data.updated_count,
        failedCount: response.data.failed_count,
        updatedIds: response.data.updated_ids,
        failedIds: response.data.failed_ids,
        errors: response.data.errors,
        message: response.data.message,
      };
    } catch (error) {
      handleApiError(error, 'Bulk-Aktualisierung');
    }
  },

  /**
   * Exportiert Dokumente
   */
  exportDocuments: async (options: FinanceExportOptions): Promise<FinanceExportResult> => {
    try {
      const response = await apiClient.post<{
        export_id: string;
        status: string;
        download_url: string | null;
        document_count: number;
        file_size_bytes: number | null;
        expires_at: string | null;
        message: string;
      }>('/finance/documents/export', {
        document_ids: options.documentIds,
        year: options.year,
        category: options.category,
        format: options.format || 'zip',
        include_files: options.includeFiles ?? true,
      });

      return {
        exportId: response.data.export_id,
        status: response.data.status as FinanceExportResult['status'],
        downloadUrl: response.data.download_url,
        documentCount: response.data.document_count,
        fileSizeBytes: response.data.file_size_bytes,
        expiresAt: response.data.expires_at,
        message: response.data.message,
      };
    } catch (error) {
      handleApiError(error, 'Export starten');
    }
  },

  // ==================== Deadline Operations ====================

  /**
   * Fetch all finance deadlines
   */
  getDeadlines: async (options?: FinanceDeadlineOptions): Promise<FinanceDeadlineListResult> => {
    try {
      const params = new URLSearchParams();
      if (options?.year) params.append('year', options.year);
      if (options?.category) params.append('category', options.category);
      if (options?.includePast !== undefined) params.append('include_past', String(options.includePast));
      if (options?.daysAhead) params.append('days_ahead', String(options.daysAhead));

      const response = await apiClient.get<FinanceDeadlineListBackend>(
        `/finance/deadlines?${params.toString()}`
      );

      return {
        items: response.data.items.map((item) => ({
          id: item.id,
          documentId: item.document_id,
          documentName: item.document_name,
          category: item.category,
          categoryLabel: item.category_label,
          year: item.year,
          deadline: item.deadline,
          type: item.deadline_type as FinanceDeadlineType,
          aktenzeichen: item.aktenzeichen,
          daysUntil: item.days_until,
        })),
        total: response.data.total,
        overdueCount: response.data.overdue_count,
        urgentCount: response.data.urgent_count,
        upcomingCount: response.data.upcoming_count,
      };
    } catch (error) {
      handleApiError(error, 'Fristen abrufen');
    }
  },
};

// ==================== Deadline Types ====================

export type FinanceDeadlineType = 'einspruchsfrist' | 'zahlungsfrist' | 'abgabefrist' | 'sonstige';

export interface FinanceDeadlineItem {
  id: string;
  documentId: string;
  documentName: string;
  category: string;
  categoryLabel: string;
  year: string;
  deadline: string;
  type: FinanceDeadlineType;
  aktenzeichen?: string;
  daysUntil: number;
}

export interface FinanceDeadlineListResult {
  items: FinanceDeadlineItem[];
  total: number;
  overdueCount: number;
  urgentCount: number;
  upcomingCount: number;
}

export interface FinanceDeadlineOptions {
  year?: string;
  category?: string;
  includePast?: boolean;
  daysAhead?: number;
}

interface FinanceDeadlineListBackend {
  items: {
    id: string;
    document_id: string;
    document_name: string;
    category: string;
    category_label: string;
    year: string;
    deadline: string;
    deadline_type: string;
    aktenzeichen?: string;
    days_until: number;
  }[];
  total: number;
  overdue_count: number;
  urgent_count: number;
  upcoming_count: number;
}

// ==================== History Types ====================

export type FinanceHistoryAction =
  | 'created'
  | 'updated'
  | 'deleted'
  | 'restored'
  | 'category_changed'
  | 'year_changed'
  | 'ocr_completed'
  | 'deadline_set'
  | 'deadline_removed'
  | 'bulk_update';

export interface FinanceHistoryItem {
  id: string;
  documentId: string;
  userId?: string;
  userEmail?: string;
  userName?: string;
  action: FinanceHistoryAction;
  description?: string;
  oldValues: Record<string, unknown>;
  newValues: Record<string, unknown>;
  changedFields: string[];
  ipAddress?: string;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface FinanceDocumentHistoryResult {
  documentId: string;
  documentName: string;
  items: FinanceHistoryItem[];
  total: number;
}

interface FinanceDocumentHistoryBackend {
  document_id: string;
  document_name: string;
  items: {
    id: string;
    document_id: string;
    user_id?: string;
    user_email?: string;
    user_name?: string;
    action: string;
    description?: string;
    old_values: Record<string, unknown>;
    new_values: Record<string, unknown>;
    changed_fields: string[];
    ip_address?: string;
    metadata: Record<string, unknown>;
    created_at: string;
  }[];
  total: number;
}

// ==================== History API Service ====================

export const financeHistoryApi = {
  /**
   * Fetch document history (audit trail)
   */
  getDocumentHistory: async (
    documentId: string,
    limit?: number
  ): Promise<FinanceDocumentHistoryResult> => {
    try {
      const params = new URLSearchParams();
      if (limit) params.append('limit', String(limit));

      const url = `/finance/documents/${documentId}/history${params.toString() ? `?${params.toString()}` : ''}`;
      const response = await apiClient.get<FinanceDocumentHistoryBackend>(url);

      return {
        documentId: response.data.document_id,
        documentName: response.data.document_name,
        items: response.data.items.map((item) => ({
          id: item.id,
          documentId: item.document_id,
          userId: item.user_id,
          userEmail: item.user_email,
          userName: item.user_name,
          action: item.action as FinanceHistoryAction,
          description: item.description,
          oldValues: item.old_values || {},
          newValues: item.new_values || {},
          changedFields: item.changed_fields || [],
          ipAddress: item.ip_address,
          metadata: item.metadata || {},
          createdAt: item.created_at,
        })),
        total: response.data.total,
      };
    } catch (error) {
      if (error instanceof AxiosError) {
        throw new FinanceApiError(
          error.response?.data?.detail || 'History konnte nicht geladen werden',
          error.response?.status,
          error
        );
      }
      throw error;
    }
  },
};

// ==================== Version Types ====================

export interface FinanceDocumentVersion {
  id: string;
  documentId: string;
  versionNumber: number;
  backend: string;
  isCurrent: boolean;
  isRollback: boolean;
  rollbackFromVersion?: number;
  confidenceScore?: number;
  wordCount?: number;
  charCount?: number;
  hasUmlauts: boolean;
  germanValidationScore?: number;
  processingTimeMs?: number;
  extractedText?: string;
  detectedDates: string[];
  detectedAmounts: { value: number; currency: string }[];
  detectedIbans: string[];
  detectedVatIds: string[];
  createdAt: string;
  createdById?: string;
  versionNote?: string;
}

export interface FinanceDocumentVersionSummary {
  id: string;
  versionNumber: number;
  backend: string;
  isCurrent: boolean;
  isRollback: boolean;
  rollbackFromVersion?: number;
  confidenceScore?: number;
  wordCount?: number;
  charCount?: number;
  hasUmlauts: boolean;
  processingTimeMs?: number;
  createdAt: string;
  versionNote?: string;
}

export interface FinanceDocumentVersionList {
  documentId: string;
  documentFilename: string;
  currentVersion: number;
  totalVersions: number;
  versions: FinanceDocumentVersionSummary[];
}

export interface FinanceVersionDiff {
  backendChanged: boolean;
  textLengthDelta: number;
  datesCountDelta: number;
  amountsCountDelta: number;
  ibansCountDelta: number;
  vatIdsCountDelta: number;
  confidenceImproved?: boolean;
}

export interface FinanceVersionCompareResult {
  documentId: string;
  versionA: FinanceDocumentVersion;
  versionB: FinanceDocumentVersion;
  differences: FinanceVersionDiff;
  textDiffUnified?: string;
  confidenceDelta?: number;
  wordCountDelta?: number;
}

export interface FinanceVersionRollbackResult {
  success: boolean;
  newVersionNumber: number;
  rolledBackFrom: number;
  message: string;
}

// Backend types for versions
interface OCRVersionBackend {
  id: string;
  document_id: string;
  version_number: number;
  backend: string;
  is_current: boolean;
  is_rollback: boolean;
  rollback_from_version?: number;
  confidence_score?: number;
  word_count?: number;
  char_count?: number;
  has_umlauts: boolean;
  german_validation_score?: number;
  processing_time_ms?: number;
  extracted_text?: string;
  detected_dates: string[];
  detected_amounts: { value: number; currency: string }[];
  detected_ibans: string[];
  detected_vat_ids: string[];
  created_at: string;
  created_by_id?: string;
  version_note?: string;
}

interface OCRVersionSummaryBackend {
  id: string;
  version_number: number;
  backend: string;
  is_current: boolean;
  is_rollback: boolean;
  rollback_from_version?: number;
  confidence_score?: number;
  word_count?: number;
  char_count?: number;
  has_umlauts: boolean;
  processing_time_ms?: number;
  created_at: string;
  version_note?: string;
}

interface OCRVersionListBackend {
  document_id: string;
  document_filename: string;
  current_version: number;
  total_versions: number;
  versions: OCRVersionSummaryBackend[];
}

interface OCRVersionCompareBackend {
  document_id: string;
  version_a: OCRVersionBackend;
  version_b: OCRVersionBackend;
  differences: {
    backend_changed: boolean;
    text_length_delta: number;
    dates_count_delta: number;
    amounts_count_delta: number;
    ibans_count_delta: number;
    vat_ids_count_delta: number;
    confidence_improved?: boolean;
  };
  text_diff_unified?: string;
  confidence_delta?: number;
  word_count_delta?: number;
}

interface OCRVersionRollbackBackend {
  success: boolean;
  new_version_number: number;
  rolled_back_from: number;
  message: string;
}

// Transform functions for versions
function transformVersion(v: OCRVersionBackend): FinanceDocumentVersion {
  return {
    id: v.id,
    documentId: v.document_id,
    versionNumber: v.version_number,
    backend: v.backend,
    isCurrent: v.is_current,
    isRollback: v.is_rollback,
    rollbackFromVersion: v.rollback_from_version,
    confidenceScore: v.confidence_score,
    wordCount: v.word_count,
    charCount: v.char_count,
    hasUmlauts: v.has_umlauts,
    germanValidationScore: v.german_validation_score,
    processingTimeMs: v.processing_time_ms,
    extractedText: v.extracted_text,
    detectedDates: v.detected_dates || [],
    detectedAmounts: v.detected_amounts || [],
    detectedIbans: v.detected_ibans || [],
    detectedVatIds: v.detected_vat_ids || [],
    createdAt: v.created_at,
    createdById: v.created_by_id,
    versionNote: v.version_note,
  };
}

function transformVersionSummary(v: OCRVersionSummaryBackend): FinanceDocumentVersionSummary {
  return {
    id: v.id,
    versionNumber: v.version_number,
    backend: v.backend,
    isCurrent: v.is_current,
    isRollback: v.is_rollback,
    rollbackFromVersion: v.rollback_from_version,
    confidenceScore: v.confidence_score,
    wordCount: v.word_count,
    charCount: v.char_count,
    hasUmlauts: v.has_umlauts,
    processingTimeMs: v.processing_time_ms,
    createdAt: v.created_at,
    versionNote: v.version_note,
  };
}

// ==================== Anomaly Types ====================

export type AnomalySeverity = 'low' | 'medium' | 'high' | 'critical';
export type AnomalyStatus = 'pending' | 'reviewed' | 'resolved';

export interface AnomalyItem {
  type: string;
  severity: AnomalySeverity;
  description: string;
  confidence: number;
  details: Record<string, unknown>;
}

export interface AnomalyCheckResult {
  documentId: string;
  documentName: string;
  isSuspicious: boolean;
  overallRiskScore: number;
  anomalyCount: number;
  anomalies: AnomalyItem[];
  checkedAt: string;
  message: string;
}

export interface AnomalyDashboardStats {
  totalDocumentsChecked: number;
  suspiciousDocuments: number;
  pendingReview: number;
  resolved: number;
  averageRiskScore: number;
  anomalyTypeDistribution: Record<string, number>;
}

export interface AnomalyDocumentSummary {
  documentId: string;
  documentName: string;
  category: string;
  year: number;
  riskScore: number;
  anomalyCount: number;
  anomalyTypes: string[];
  detectedAt: string;
  status: AnomalyStatus;
}

export interface AnomalyDashboardResult {
  stats: AnomalyDashboardStats;
  recentAnomalies: AnomalyDocumentSummary[];
  message: string;
}

// Backend types
interface AnomalyCheckBackend {
  document_id: string;
  document_name: string;
  is_suspicious: boolean;
  overall_risk_score: number;
  anomaly_count: number;
  anomalies: {
    type: string;
    severity: string;
    description: string;
    confidence: number;
    details: Record<string, unknown>;
  }[];
  checked_at: string;
  message: string;
}

interface AnomalyDashboardBackend {
  stats: {
    total_documents_checked: number;
    suspicious_documents: number;
    pending_review: number;
    resolved: number;
    average_risk_score: number;
    anomaly_type_distribution: Record<string, number>;
  };
  recent_anomalies: {
    document_id: string;
    document_name: string;
    category: string;
    year: number;
    risk_score: number;
    anomaly_count: number;
    anomaly_types: string[];
    detected_at: string;
    status: string;
  }[];
  message: string;
}

// ==================== Anomaly API Service ====================

export const financeAnomalyApi = {
  /**
   * Check a document for anomalies
   */
  checkDocument: async (documentId: string): Promise<AnomalyCheckResult> => {
    try {
      const response = await apiClient.post<AnomalyCheckBackend>(
        `/finance/anomalies/check/${documentId}`
      );

      return {
        documentId: response.data.document_id,
        documentName: response.data.document_name,
        isSuspicious: response.data.is_suspicious,
        overallRiskScore: response.data.overall_risk_score,
        anomalyCount: response.data.anomaly_count,
        anomalies: response.data.anomalies.map((a) => ({
          type: a.type,
          severity: a.severity as AnomalySeverity,
          description: a.description,
          confidence: a.confidence,
          details: a.details,
        })),
        checkedAt: response.data.checked_at,
        message: response.data.message,
      };
    } catch (error) {
      handleApiError(error, 'Anomalie-Prüfung');
    }
  },

  /**
   * Get anomaly dashboard with statistics
   */
  getDashboard: async (options?: { year?: number; limit?: number }): Promise<AnomalyDashboardResult> => {
    try {
      const params = new URLSearchParams();
      if (options?.year) params.append('year', String(options.year));
      if (options?.limit) params.append('limit', String(options.limit));

      const url = `/finance/anomalies/dashboard${params.toString() ? `?${params.toString()}` : ''}`;
      const response = await apiClient.get<AnomalyDashboardBackend>(url);

      return {
        stats: {
          totalDocumentsChecked: response.data.stats.total_documents_checked,
          suspiciousDocuments: response.data.stats.suspicious_documents,
          pendingReview: response.data.stats.pending_review,
          resolved: response.data.stats.resolved,
          averageRiskScore: response.data.stats.average_risk_score,
          anomalyTypeDistribution: response.data.stats.anomaly_type_distribution,
        },
        recentAnomalies: response.data.recent_anomalies.map((a) => ({
          documentId: a.document_id,
          documentName: a.document_name,
          category: a.category,
          year: a.year,
          riskScore: a.risk_score,
          anomalyCount: a.anomaly_count,
          anomalyTypes: a.anomaly_types,
          detectedAt: a.detected_at,
          status: a.status as AnomalyStatus,
        })),
        message: response.data.message,
      };
    } catch (error) {
      // Return empty result on error (dashboard should still render)
      if (error instanceof AxiosError && error.response?.status === 404) {
        return {
          stats: {
            totalDocumentsChecked: 0,
            suspiciousDocuments: 0,
            pendingReview: 0,
            resolved: 0,
            averageRiskScore: 0,
            anomalyTypeDistribution: {},
          },
          recentAnomalies: [],
          message: 'Keine Anomalien gefunden',
        };
      }
      handleApiError(error, 'Anomalie-Dashboard laden');
    }
  },
};

// ==================== Version API Service ====================

export const financeVersionApi = {
  /**
   * Fetch all versions for a document
   */
  getVersions: async (
    documentId: string,
    limit = 50,
    offset = 0
  ): Promise<FinanceDocumentVersionList> => {
    try {
      const params = new URLSearchParams();
      params.append('limit', String(limit));
      params.append('offset', String(offset));

      const response = await apiClient.get<OCRVersionListBackend>(
        `/documents/${documentId}/versions/?${params.toString()}`
      );

      return {
        documentId: response.data.document_id,
        documentFilename: response.data.document_filename,
        currentVersion: response.data.current_version,
        totalVersions: response.data.total_versions,
        versions: response.data.versions.map(transformVersionSummary),
      };
    } catch (error) {
      handleApiError(error, 'Versionen abrufen');
    }
  },

  /**
   * Fetch a specific version
   */
  getVersion: async (
    documentId: string,
    versionNumber: number
  ): Promise<FinanceDocumentVersion> => {
    try {
      const response = await apiClient.get<OCRVersionBackend>(
        `/documents/${documentId}/versions/${versionNumber}`
      );

      return transformVersion(response.data);
    } catch (error) {
      handleApiError(error, 'Version abrufen');
    }
  },

  /**
   * Fetch current version
   */
  getCurrentVersion: async (documentId: string): Promise<FinanceDocumentVersion> => {
    try {
      const response = await apiClient.get<OCRVersionBackend>(
        `/documents/${documentId}/versions/current`
      );

      return transformVersion(response.data);
    } catch (error) {
      handleApiError(error, 'Aktuelle Version abrufen');
    }
  },

  /**
   * Compare two versions
   */
  compareVersions: async (
    documentId: string,
    versionA: number,
    versionB: number
  ): Promise<FinanceVersionCompareResult> => {
    try {
      const response = await apiClient.post<OCRVersionCompareBackend>(
        `/documents/${documentId}/versions/compare`,
        { version_a: versionA, version_b: versionB }
      );

      return {
        documentId: response.data.document_id,
        versionA: transformVersion(response.data.version_a),
        versionB: transformVersion(response.data.version_b),
        differences: {
          backendChanged: response.data.differences.backend_changed,
          textLengthDelta: response.data.differences.text_length_delta,
          datesCountDelta: response.data.differences.dates_count_delta,
          amountsCountDelta: response.data.differences.amounts_count_delta,
          ibansCountDelta: response.data.differences.ibans_count_delta,
          vatIdsCountDelta: response.data.differences.vat_ids_count_delta,
          confidenceImproved: response.data.differences.confidence_improved,
        },
        textDiffUnified: response.data.text_diff_unified,
        confidenceDelta: response.data.confidence_delta,
        wordCountDelta: response.data.word_count_delta,
      };
    } catch (error) {
      handleApiError(error, 'Versionen vergleichen');
    }
  },

  /**
   * Rollback to a previous version
   */
  rollbackToVersion: async (
    documentId: string,
    targetVersion: number,
    rollbackNote?: string
  ): Promise<FinanceVersionRollbackResult> => {
    try {
      const response = await apiClient.post<OCRVersionRollbackBackend>(
        `/documents/${documentId}/versions/rollback`,
        { target_version: targetVersion, rollback_note: rollbackNote }
      );

      return {
        success: response.data.success,
        newVersionNumber: response.data.new_version_number,
        rolledBackFrom: response.data.rolled_back_from,
        message: response.data.message,
      };
    } catch (error) {
      handleApiError(error, 'Rollback durchführen');
    }
  },
};
