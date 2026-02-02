/**
 * Bulk Operations API
 *
 * API-Funktionen fuer Massenaktionen auf Dokumenten.
 *
 * Unterstuetzte Aktionen:
 * - tag: Tags hinzufuegen/entfernen/ersetzen
 * - move: In Ordner verschieben
 * - delete: Soft-Delete (GDPR-konform)
 * - export: Exportieren (ZIP, PDF, CSV)
 * - categorize: Kategorie setzen
 */

import { apiClient } from '@/lib/api/client';

// =============================================================================
// Types
// =============================================================================

export type BulkAction = 'tag' | 'move' | 'delete' | 'export' | 'categorize';

export type TagOperation = 'add' | 'remove' | 'set';

export type ExportFormat = 'zip' | 'pdf' | 'csv';

export interface BulkOperationParams {
  /** Fuer tag-Aktion */
  tags?: string[];
  operation?: TagOperation;

  /** Fuer move-Aktion */
  folder_id?: string;

  /** Fuer delete-Aktion */
  reason?: string;

  /** Fuer export-Aktion */
  format?: ExportFormat;
  include_metadata?: boolean;

  /** Fuer categorize-Aktion */
  category?: string;
}

export interface BulkOperationRequest {
  document_ids: string[];
  action: BulkAction;
  params?: BulkOperationParams;
}

export interface BulkOperationError {
  id: string;
  error: string;
}

export interface BulkOperationResponse {
  success: boolean;
  action: string;
  total_requested: number;
  processed: number;
  failed: number;
  errors: BulkOperationError[];
  message: string;
  task_id?: string;
  download_url?: string;
}

// Frontend-friendly response (camelCase)
export interface BulkOperationResult {
  success: boolean;
  action: BulkAction;
  totalRequested: number;
  processed: number;
  failed: number;
  errors: Array<{ documentId: string; error: string }>;
  message: string;
  taskId?: string;
  downloadUrl?: string;
}

// =============================================================================
// Transformer
// =============================================================================

function transformResponse(response: BulkOperationResponse): BulkOperationResult {
  return {
    success: response.success,
    action: response.action as BulkAction,
    totalRequested: response.total_requested,
    processed: response.processed,
    failed: response.failed,
    errors: response.errors.map((e) => ({
      documentId: e.id,
      error: e.error,
    })),
    message: response.message,
    taskId: response.task_id,
    downloadUrl: response.download_url,
  };
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Fuehrt eine Bulk-Operation auf mehreren Dokumenten aus.
 *
 * @param request - Die Bulk-Operation-Anfrage
 * @returns Das Ergebnis der Operation
 */
export async function executeBulkOperation(
  request: BulkOperationRequest
): Promise<BulkOperationResult> {
  const response = await apiClient.post<BulkOperationResponse>(
    '/documents/bulk',
    request
  );
  return transformResponse(response.data);
}

/**
 * Tags zu mehreren Dokumenten hinzufuegen.
 */
export async function bulkAddTags(
  documentIds: string[],
  tags: string[]
): Promise<BulkOperationResult> {
  return executeBulkOperation({
    document_ids: documentIds,
    action: 'tag',
    params: { tags, operation: 'add' },
  });
}

/**
 * Tags von mehreren Dokumenten entfernen.
 */
export async function bulkRemoveTags(
  documentIds: string[],
  tags: string[]
): Promise<BulkOperationResult> {
  return executeBulkOperation({
    document_ids: documentIds,
    action: 'tag',
    params: { tags, operation: 'remove' },
  });
}

/**
 * Tags von mehreren Dokumenten ersetzen.
 */
export async function bulkSetTags(
  documentIds: string[],
  tags: string[]
): Promise<BulkOperationResult> {
  return executeBulkOperation({
    document_ids: documentIds,
    action: 'tag',
    params: { tags, operation: 'set' },
  });
}

/**
 * Mehrere Dokumente in einen Ordner verschieben.
 */
export async function bulkMoveToFolder(
  documentIds: string[],
  folderId: string
): Promise<BulkOperationResult> {
  return executeBulkOperation({
    document_ids: documentIds,
    action: 'move',
    params: { folder_id: folderId },
  });
}

/**
 * Mehrere Dokumente loeschen (Soft-Delete).
 */
export async function bulkDeleteDocuments(
  documentIds: string[],
  reason?: string
): Promise<BulkOperationResult> {
  return executeBulkOperation({
    document_ids: documentIds,
    action: 'delete',
    params: reason ? { reason } : undefined,
  });
}

/**
 * Mehrere Dokumente exportieren.
 */
export async function bulkExportDocuments(
  documentIds: string[],
  format: ExportFormat = 'zip',
  includeMetadata: boolean = true
): Promise<BulkOperationResult> {
  return executeBulkOperation({
    document_ids: documentIds,
    action: 'export',
    params: { format, include_metadata: includeMetadata },
  });
}

/**
 * Kategorie fuer mehrere Dokumente setzen.
 */
export async function bulkCategorizeDocuments(
  documentIds: string[],
  category: string
): Promise<BulkOperationResult> {
  return executeBulkOperation({
    document_ids: documentIds,
    action: 'categorize',
    params: { category },
  });
}
