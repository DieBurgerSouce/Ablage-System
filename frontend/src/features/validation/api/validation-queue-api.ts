/**
 * Validation Queue API Client
 *
 * API-Client für das Enterprise-Grade Validierungs-Queue-System.
 * Basiert auf den Backend-Endpoints in app/api/v1/validation.py
 */

import { apiClient } from '@/lib/api-client';
import type {
  ValidationQueueItem,
  ValidationQueueItemDetail,
  ValidationQueueListResponse,
  ValidationQueueItemCreate,
  ValidationQueueItemUpdate,
  ValidationQueueItemAssign,
  ValidationQueueItemApprove,
  ValidationQueueItemReject,
  ValidationFieldReview,
  ValidationFieldUpdate,
  ValidationFieldValidateResult,
  ValidationRule,
  ValidationRuleCreate,
  ValidationRuleUpdate,
  ValidationRuleListResponse,
  ValidationSampleConfig,
  ValidationSampleConfigUpdate,
  BatchApproveRequest,
  BatchRejectRequest,
  BatchAssignRequest,
  BatchOperationResult,
  ValidationAnalyticsOverview,
  EditorStats,
  EditorStatsListResponse,
  TrendDataPoint,
  TrendDataResponse,
  DocumentTypeStats,
  DocumentTypeStatsResponse,
  ConfidenceDistribution,
  ValidationQueueFilters,
  ValidationQueueSortOptions,
  ValidationStatus,
  SampleSource,
} from '../types/validation-queue.types';

const BASE_URL = '/api/v1/validation';

// ==================== Query Keys ====================

export const validationQueryKeys = {
  all: ['validation'] as const,
  // Stabile Query-Keys durch JSON-Serialisierung des Filter-Objekts
  queue: (filters?: ValidationQueueFilters) => [
    ...validationQueryKeys.all,
    'queue',
    filters ? JSON.stringify(filters) : undefined,
  ] as const,
  queueItem: (id: string) => [...validationQueryKeys.all, 'queue', 'item', id] as const,
  queueStats: () => [...validationQueryKeys.all, 'queue', 'stats'] as const,
  myItems: () => [...validationQueryKeys.all, 'queue', 'my-items'] as const,
  fields: (itemId: string) => [...validationQueryKeys.all, 'fields', itemId] as const,
  fieldStats: (itemId: string) => [...validationQueryKeys.all, 'field-stats', itemId] as const,
  rules: () => [...validationQueryKeys.all, 'rules'] as const,
  rule: (id: string) => [...validationQueryKeys.all, 'rules', id] as const,
  sampleConfig: () => [...validationQueryKeys.all, 'sample-config'] as const,
  analyticsOverview: (dateFrom?: string, dateTo?: string) =>
    [...validationQueryKeys.all, 'analytics', 'overview', dateFrom, dateTo] as const,
  editorStats: (dateFrom?: string, dateTo?: string) =>
    [...validationQueryKeys.all, 'analytics', 'editors', dateFrom, dateTo] as const,
  trends: (days?: number, groupBy?: string) =>
    [...validationQueryKeys.all, 'analytics', 'trends', days, groupBy] as const,
  documentTypes: () => [...validationQueryKeys.all, 'analytics', 'document-types'] as const,
  confidenceDistribution: () => [...validationQueryKeys.all, 'analytics', 'confidence'] as const,
};

// ==================== Queue Management ====================

export interface ListQueueParams extends ValidationQueueFilters, ValidationQueueSortOptions {
  limit?: number;
  offset?: number;
}

/**
 * Listet Validierungs-Queue-Items mit optionalen Filtern auf.
 */
export async function listQueueItems(
  params: ListQueueParams = {}
): Promise<ValidationQueueListResponse> {
  const searchParams = new URLSearchParams();

  if (params.status) {
    searchParams.append('status', params.status);
  }
  if (params.document_type) {
    searchParams.append('document_type', params.document_type);
  }
  if (params.priority_min !== undefined) {
    searchParams.append('priority_min', String(params.priority_min));
  }
  if (params.priority_max !== undefined) {
    searchParams.append('priority_max', String(params.priority_max));
  }
  if (params.confidence_min !== undefined) {
    searchParams.append('confidence_min', String(params.confidence_min));
  }
  if (params.confidence_max !== undefined) {
    searchParams.append('confidence_max', String(params.confidence_max));
  }
  if (params.assigned_to_id) {
    searchParams.append('assigned_to_id', params.assigned_to_id);
  }
  if (params.sample_source) {
    searchParams.append('sample_source', params.sample_source);
  }
  if (params.created_from) {
    searchParams.append('created_from', params.created_from);
  }
  if (params.created_to) {
    searchParams.append('created_to', params.created_to);
  }
  if (params.sort_by) {
    searchParams.append('sort_by', params.sort_by);
  }
  if (params.sort_order) {
    searchParams.append('sort_order', params.sort_order);
  }
  if (params.limit) {
    searchParams.append('limit', String(params.limit));
  }
  if (params.offset) {
    searchParams.append('offset', String(params.offset));
  }

  const url = `${BASE_URL}/queue${searchParams.toString() ? `?${searchParams}` : ''}`;
  const response = await apiClient.get<ValidationQueueListResponse>(url);
  return response.data;
}

/**
 * Holt Queue-Statistiken.
 */
export async function getQueueStats(): Promise<Record<string, number>> {
  const response = await apiClient.get<Record<string, number>>(`${BASE_URL}/queue/stats`);
  return response.data;
}

/**
 * Holt die dem aktuellen Benutzer zugewiesenen Items.
 */
export async function getMyAssignedItems(
  status?: ValidationStatus,
  limit = 50,
  offset = 0
): Promise<ValidationQueueListResponse> {
  const searchParams = new URLSearchParams();
  if (status) {
    searchParams.append('status', status);
  }
  searchParams.append('limit', String(limit));
  searchParams.append('offset', String(offset));

  const response = await apiClient.get<ValidationQueueListResponse>(
    `${BASE_URL}/queue/my-items?${searchParams}`
  );
  return response.data;
}

/**
 * Erstellt ein neues Queue-Item (manuelles Hinzufügen).
 */
export async function createQueueItem(
  data: ValidationQueueItemCreate
): Promise<ValidationQueueItem> {
  const response = await apiClient.post<ValidationQueueItem>(`${BASE_URL}/queue`, data);
  return response.data;
}

/**
 * Holt ein einzelnes Queue-Item mit Details.
 */
export async function getQueueItem(itemId: string): Promise<ValidationQueueItemDetail> {
  const response = await apiClient.get<ValidationQueueItemDetail>(`${BASE_URL}/queue/${itemId}`);
  return response.data;
}

/**
 * Aktualisiert ein Queue-Item.
 */
export async function updateQueueItem(
  itemId: string,
  data: ValidationQueueItemUpdate
): Promise<ValidationQueueItem> {
  const response = await apiClient.patch<ValidationQueueItem>(`${BASE_URL}/queue/${itemId}`, data);
  return response.data;
}

/**
 * Löscht ein Queue-Item.
 */
export async function deleteQueueItem(itemId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/queue/${itemId}`);
}

// ==================== Assignment ====================

/**
 * Weist ein Queue-Item einem Editor zu.
 */
export async function assignQueueItem(
  itemId: string,
  data: ValidationQueueItemAssign
): Promise<ValidationQueueItem> {
  const response = await apiClient.post<ValidationQueueItem>(
    `${BASE_URL}/queue/${itemId}/assign`,
    data
  );
  return response.data;
}

/**
 * Entfernt die Zuweisung eines Queue-Items.
 */
export async function unassignQueueItem(itemId: string): Promise<ValidationQueueItem> {
  const response = await apiClient.post<ValidationQueueItem>(
    `${BASE_URL}/queue/${itemId}/unassign`
  );
  return response.data;
}

// ==================== Approval / Rejection ====================

/**
 * Genehmigt ein Queue-Item.
 */
export async function approveQueueItem(
  itemId: string,
  data: ValidationQueueItemApprove = {}
): Promise<ValidationQueueItem> {
  const response = await apiClient.post<ValidationQueueItem>(
    `${BASE_URL}/queue/${itemId}/approve`,
    data
  );
  return response.data;
}

/**
 * Lehnt ein Queue-Item ab.
 */
export async function rejectQueueItem(
  itemId: string,
  data: ValidationQueueItemReject
): Promise<ValidationQueueItem> {
  const response = await apiClient.post<ValidationQueueItem>(
    `${BASE_URL}/queue/${itemId}/reject`,
    data
  );
  return response.data;
}

// ==================== Batch Operations ====================

/**
 * Genehmigt mehrere Queue-Items gleichzeitig.
 */
export async function batchApprove(data: BatchApproveRequest): Promise<BatchOperationResult> {
  const response = await apiClient.post<BatchOperationResult>(`${BASE_URL}/batch/approve`, data);
  return response.data;
}

/**
 * Lehnt mehrere Queue-Items gleichzeitig ab.
 */
export async function batchReject(data: BatchRejectRequest): Promise<BatchOperationResult> {
  const response = await apiClient.post<BatchOperationResult>(`${BASE_URL}/batch/reject`, data);
  return response.data;
}

/**
 * Weist mehrere Queue-Items einem Editor zu.
 */
export async function batchAssign(data: BatchAssignRequest): Promise<BatchOperationResult> {
  const response = await apiClient.post<BatchOperationResult>(`${BASE_URL}/batch/assign`, data);
  return response.data;
}

// ==================== Field Reviews ====================

/**
 * Holt alle Feld-Reviews für ein Queue-Item.
 */
export async function getQueueItemFields(itemId: string): Promise<ValidationFieldReview[]> {
  const response = await apiClient.get<ValidationFieldReview[]>(`${BASE_URL}/queue/${itemId}/fields`);
  return response.data;
}

/**
 * Aktualisiert einen Feldwert.
 */
export async function updateField(
  itemId: string,
  fieldId: string,
  data: ValidationFieldUpdate
): Promise<ValidationFieldReview> {
  const response = await apiClient.patch<ValidationFieldReview>(
    `${BASE_URL}/queue/${itemId}/fields/${fieldId}`,
    data
  );
  return response.data;
}

/**
 * Validiert ein einzelnes Feld.
 */
export async function validateField(
  itemId: string,
  fieldId: string
): Promise<ValidationFieldValidateResult> {
  const response = await apiClient.post<ValidationFieldValidateResult>(
    `${BASE_URL}/queue/${itemId}/fields/${fieldId}/validate`
  );
  return response.data;
}

/**
 * Validiert alle Felder eines Queue-Items.
 */
export async function validateAllFields(itemId: string): Promise<ValidationFieldValidateResult[]> {
  const response = await apiClient.post<ValidationFieldValidateResult[]>(
    `${BASE_URL}/queue/${itemId}/validate-all`
  );
  return response.data;
}

/**
 * Holt Feld-Statistiken für ein Queue-Item.
 */
export async function getFieldStats(itemId: string): Promise<Record<string, unknown>> {
  const response = await apiClient.get<Record<string, unknown>>(
    `${BASE_URL}/queue/${itemId}/field-stats`
  );
  return response.data;
}

// ==================== Rules ====================

/**
 * Listet alle Validierungsregeln auf.
 */
export async function listRules(includeInactive = false): Promise<ValidationRuleListResponse> {
  const params = includeInactive ? '?include_inactive=true' : '';
  const response = await apiClient.get<ValidationRuleListResponse>(`${BASE_URL}/rules${params}`);
  return response.data;
}

/**
 * Erstellt eine neue Regel.
 */
export async function createRule(data: ValidationRuleCreate): Promise<ValidationRule> {
  const response = await apiClient.post<ValidationRule>(`${BASE_URL}/rules`, data);
  return response.data;
}

/**
 * Holt eine einzelne Regel.
 */
export async function getRule(ruleId: string): Promise<ValidationRule> {
  const response = await apiClient.get<ValidationRule>(`${BASE_URL}/rules/${ruleId}`);
  return response.data;
}

/**
 * Aktualisiert eine Regel.
 */
export async function updateRule(
  ruleId: string,
  data: ValidationRuleUpdate
): Promise<ValidationRule> {
  const response = await apiClient.patch<ValidationRule>(`${BASE_URL}/rules/${ruleId}`, data);
  return response.data;
}

/**
 * Löscht eine Regel.
 */
export async function deleteRule(ruleId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/rules/${ruleId}`);
}

// ==================== Sample Config ====================

/**
 * Holt die aktuelle Stichproben-Konfiguration.
 */
export async function getSampleConfig(): Promise<ValidationSampleConfig> {
  const response = await apiClient.get<ValidationSampleConfig>(`${BASE_URL}/sample-config`);
  return response.data;
}

/**
 * Aktualisiert die Stichproben-Konfiguration.
 */
export async function updateSampleConfig(
  configId: string,
  data: ValidationSampleConfigUpdate
): Promise<ValidationSampleConfig> {
  const response = await apiClient.put<ValidationSampleConfig>(
    `${BASE_URL}/sample-config/${configId}`,
    data
  );
  return response.data;
}

// ==================== Analytics ====================

/**
 * Holt Übersichtsstatistiken zur Validierung.
 */
export async function getAnalyticsOverview(
  dateFrom?: string,
  dateTo?: string
): Promise<ValidationAnalyticsOverview> {
  const searchParams = new URLSearchParams();
  if (dateFrom) {
    searchParams.append('date_from', dateFrom);
  }
  if (dateTo) {
    searchParams.append('date_to', dateTo);
  }

  const url = `${BASE_URL}/analytics/overview${searchParams.toString() ? `?${searchParams}` : ''}`;
  const response = await apiClient.get<ValidationAnalyticsOverview>(url);
  return response.data;
}

/**
 * Holt Statistiken pro Editor.
 */
export async function getEditorStats(
  dateFrom?: string,
  dateTo?: string
): Promise<EditorStatsListResponse> {
  const searchParams = new URLSearchParams();
  if (dateFrom) {
    searchParams.append('date_from', dateFrom);
  }
  if (dateTo) {
    searchParams.append('date_to', dateTo);
  }

  const url = `${BASE_URL}/analytics/editors${searchParams.toString() ? `?${searchParams}` : ''}`;
  const response = await apiClient.get<EditorStatsListResponse>(url);
  return response.data;
}

/**
 * Holt Trend-Daten über Zeit.
 */
export async function getTrends(
  days = 30,
  groupBy: 'day' | 'week' | 'month' = 'day'
): Promise<TrendDataResponse> {
  const response = await apiClient.get<TrendDataResponse>(
    `${BASE_URL}/analytics/trends?days=${days}&group_by=${groupBy}`
  );
  return response.data;
}

/**
 * Holt Statistiken nach Dokumenttyp.
 */
export async function getDocumentTypeStats(): Promise<DocumentTypeStatsResponse> {
  const response = await apiClient.get<DocumentTypeStatsResponse>(
    `${BASE_URL}/analytics/document-types`
  );
  return response.data;
}

/**
 * Holt die Confidence-Verteilung.
 */
export async function getConfidenceDistribution(): Promise<ConfidenceDistribution> {
  const response = await apiClient.get<ConfidenceDistribution>(
    `${BASE_URL}/analytics/confidence-distribution`
  );
  return response.data;
}

// ==================== Document Integration ====================

/**
 * Fügt ein Dokument manuell zur Validierungswarteschlange hinzu.
 */
export async function queueDocumentForValidation(
  documentId: string,
  priority = 50,
  notes?: string
): Promise<ValidationQueueItem> {
  const searchParams = new URLSearchParams();
  searchParams.append('priority', String(priority));
  if (notes) {
    searchParams.append('notes', notes);
  }

  const response = await apiClient.post<ValidationQueueItem>(
    `${BASE_URL}/documents/${documentId}/queue-for-validation?${searchParams}`
  );
  return response.data;
}

// ==================== Export Object ====================

export const validationQueueApi = {
  // Query Keys
  queryKeys: validationQueryKeys,

  // Queue Management
  listQueue: listQueueItems,
  getQueueStats,
  getMyItems: getMyAssignedItems,
  createQueueItem,
  getQueueItem,
  updateQueueItem,
  deleteQueueItem,

  // Assignment
  assignItem: assignQueueItem,
  unassignItem: unassignQueueItem,

  // Approval/Rejection
  approveItem: approveQueueItem,
  rejectItem: rejectQueueItem,

  // Batch Operations
  batchApprove,
  batchReject,
  batchAssign,

  // Field Reviews
  getFields: getQueueItemFields,
  updateField,
  validateField,
  validateAllFields,
  getFieldStats,

  // Rules
  listRules,
  createRule,
  getRule,
  updateRule,
  deleteRule,

  // Sample Config
  getSampleConfig,
  updateSampleConfig,

  // Analytics
  getOverview: getAnalyticsOverview,
  getEditorStats,
  getTrends,
  getDocumentTypeStats,
  getConfidenceDistribution,

  // Document Integration
  queueDocument: queueDocumentForValidation,
};

export default validationQueueApi;
