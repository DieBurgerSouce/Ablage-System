/**
 * Document Bulk Operations Module
 *
 * Stellt alle Komponenten und Hooks fuer Massenoperationen auf Dokumenten bereit.
 *
 * Exports:
 * - API functions: executeBulkOperation, bulkAddTags, bulkMoveToFolder, etc.
 * - Hooks: useDocumentBulkOperations
 * - Components: DocumentBulkActionsBar
 * - Types: BulkAction, BulkOperationResult, etc.
 */

// API
export {
  executeBulkOperation,
  bulkAddTags,
  bulkRemoveTags,
  bulkSetTags,
  bulkMoveToFolder,
  bulkDeleteDocuments,
  bulkExportDocuments,
  bulkCategorizeDocuments,
  type BulkAction,
  type TagOperation,
  type ExportFormat,
  type BulkOperationParams,
  type BulkOperationRequest,
  type BulkOperationResult,
  type BulkOperationError,
} from './api';

// Hooks
export {
  useDocumentBulkOperations,
  type UseDocumentBulkOperationsOptions,
  type UseDocumentBulkOperationsReturn,
} from './hooks';

// Components
export {
  DocumentBulkActionsBar,
  type DocumentBulkActionsBarProps,
  type Folder,
} from './components/DocumentBulkActionsBar';
