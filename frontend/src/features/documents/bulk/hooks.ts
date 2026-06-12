/**
 * Document Bulk Operations Hooks
 *
 * React Hooks für Massenaktionen auf Dokumenten mit TanStack Query.
 *
 * Features:
 * - Selection State Management (via useBulkSelection)
 * - Optimistic Updates
 * - Error Handling mit Toast-Benachrichtigungen
 * - Progress Tracking
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useCallback, useRef } from 'react';
import {
  bulkAddTags,
  bulkRemoveTags,
  bulkSetTags,
  bulkMoveToFolder,
  bulkDeleteDocuments,
  bulkExportDocuments,
  bulkCategorizeDocuments,
  type BulkOperationResult,
  type ExportFormat,
} from './api';
import {
  useBulkSelection,
  useBatchProgress,
  type UseBulkSelectionOptions,
} from '@/hooks/use-bulk-selection';
import type { Document } from '../types';

// =============================================================================
// Types
// =============================================================================

export interface UseDocumentBulkOperationsOptions extends UseBulkSelectionOptions {
  /** Query-Key für Invalidierung */
  queryKey?: string[];
  /** Callback nach erfolgreicher Operation */
  onSuccess?: (result: BulkOperationResult, action: string) => void;
  /** Callback nach fehlgeschlagener Operation */
  onError?: (error: Error, action: string) => void;
}

export interface UseDocumentBulkOperationsReturn {
  // Selection State
  selectedIds: string[];
  selectedCount: number;
  isSelected: (id: string) => boolean;
  toggleSelection: (id: string, document: Document) => void;
  selectAll: (documents: Document[]) => void;
  clearSelection: () => void;
  selectRange: (fromId: string, toId: string, allDocuments: Document[]) => void;

  // Progress
  progress: {
    action: string;
    current: number;
    total: number;
    status: 'running' | 'success' | 'error';
    message?: string;
  } | null;

  // Operations
  addTags: (tags: string[]) => Promise<void>;
  removeTags: (tags: string[]) => Promise<void>;
  setTags: (tags: string[]) => Promise<void>;
  moveToFolder: (folderId: string) => Promise<void>;
  deleteDocuments: (reason?: string) => Promise<void>;
  exportDocuments: (format?: ExportFormat, includeMetadata?: boolean) => Promise<void>;
  categorize: (category: string) => Promise<void>;

  // Loading States
  isTagging: boolean;
  isMoving: boolean;
  isDeleting: boolean;
  isExporting: boolean;
  isCategorizing: boolean;
  isAnyOperationPending: boolean;
}

// =============================================================================
// Hook
// =============================================================================

export function useDocumentBulkOperations(
  options: UseDocumentBulkOperationsOptions = {}
): UseDocumentBulkOperationsReturn {
  const { queryKey, onSuccess, onError, ...selectionOptions } = options;

  const queryClient = useQueryClient();
  const lastAnchorRef = useRef<string | null>(null);

  // Selection hook
  const {
    selectedIds,
    selectedItems: _selectedItems,
    selectedCount,
    isSelected,
    toggleSelection: baseToggleSelection,
    selectAll: baseSelectAll,
    clearSelection,
    selectRange: baseSelectRange,
    removeFromSelection,
  } = useBulkSelection<Document>(selectionOptions);

  // Progress tracking
  const { progress, startBatch, completeBatch } = useBatchProgress();

  // Helper to get document ID
  const getDocumentId = useCallback((doc: Document) => doc.id, []);

  // Enhanced toggle with anchor tracking
  const toggleSelection = useCallback(
    (id: string, document: Document) => {
      baseToggleSelection(id, document);
      lastAnchorRef.current = id;
    },
    [baseToggleSelection]
  );

  // Select all
  const selectAll = useCallback(
    (documents: Document[]) => {
      baseSelectAll(documents, getDocumentId);
    },
    [baseSelectAll, getDocumentId]
  );

  // Range selection with Shift+Click
  const selectRange = useCallback(
    (fromId: string, toId: string, allDocuments: Document[]) => {
      baseSelectRange(fromId, toId, allDocuments, getDocumentId);
    },
    [baseSelectRange, getDocumentId]
  );

  // Invalidate queries after successful operation
  const invalidateQueries = useCallback(async () => {
    if (queryKey) {
      await queryClient.invalidateQueries({ queryKey });
    }
    // Also invalidate common document queries
    await queryClient.invalidateQueries({ queryKey: ['documents'] });
    await queryClient.invalidateQueries({ queryKey: ['document-list'] });
    await queryClient.invalidateQueries({ queryKey: ['ablage'] });
  }, [queryClient, queryKey]);

  // Handle operation result
  const handleResult = useCallback(
    (result: BulkOperationResult, actionName: string, successMsg: string) => {
      if (result.success) {
        completeBatch(true, result.message);
        toast.success(successMsg, {
          description: result.message,
        });
        // Remove processed documents from selection on delete
        if (actionName === 'delete') {
          removeFromSelection(selectedIds);
        }
        onSuccess?.(result, actionName);
      } else {
        completeBatch(false, result.message);
        toast.error('Operation teilweise fehlgeschlagen', {
          description: `${result.processed} von ${result.totalRequested} Dokumenten verarbeitet`,
        });
      }
      invalidateQueries();
    },
    [completeBatch, invalidateQueries, onSuccess, removeFromSelection, selectedIds]
  );

  // Handle operation error
  const handleError = useCallback(
    (error: Error, actionName: string) => {
      completeBatch(false, error.message);
      toast.error('Operation fehlgeschlagen', {
        description: error.message,
      });
      onError?.(error, actionName);
    },
    [completeBatch, onError]
  );

  // =============================================================================
  // Mutations
  // =============================================================================

  // Tag mutations
  const addTagsMutation = useMutation({
    mutationFn: (tags: string[]) => bulkAddTags(selectedIds, tags),
    onMutate: () => startBatch('Tags hinzufügen', selectedCount),
    onSuccess: (result) =>
      handleResult(result, 'tag', `Tags zu ${result.processed} Dokumenten hinzugefügt`),
    onError: (error: Error) => handleError(error, 'tag'),
  });

  const removeTagsMutation = useMutation({
    mutationFn: (tags: string[]) => bulkRemoveTags(selectedIds, tags),
    onMutate: () => startBatch('Tags entfernen', selectedCount),
    onSuccess: (result) =>
      handleResult(result, 'tag', `Tags von ${result.processed} Dokumenten entfernt`),
    onError: (error: Error) => handleError(error, 'tag'),
  });

  const setTagsMutation = useMutation({
    mutationFn: (tags: string[]) => bulkSetTags(selectedIds, tags),
    onMutate: () => startBatch('Tags ersetzen', selectedCount),
    onSuccess: (result) =>
      handleResult(result, 'tag', `Tags für ${result.processed} Dokumente ersetzt`),
    onError: (error: Error) => handleError(error, 'tag'),
  });

  // Move mutation
  const moveMutation = useMutation({
    mutationFn: (folderId: string) => bulkMoveToFolder(selectedIds, folderId),
    onMutate: () => startBatch('Verschieben', selectedCount),
    onSuccess: (result) =>
      handleResult(result, 'move', `${result.processed} Dokumente verschoben`),
    onError: (error: Error) => handleError(error, 'move'),
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (reason?: string) => bulkDeleteDocuments(selectedIds, reason),
    onMutate: () => startBatch('Löschen', selectedCount),
    onSuccess: (result) =>
      handleResult(result, 'delete', `${result.processed} Dokumente gelöscht`),
    onError: (error: Error) => handleError(error, 'delete'),
  });

  // Export mutation
  const exportMutation = useMutation({
    mutationFn: ({ format, includeMetadata }: { format: ExportFormat; includeMetadata: boolean }) =>
      bulkExportDocuments(selectedIds, format, includeMetadata),
    onMutate: () => startBatch('Exportieren', selectedCount),
    onSuccess: (result) => {
      completeBatch(true, result.message);
      toast.success('Export gestartet', {
        description: result.taskId
          ? `Task-ID: ${result.taskId}. Sie werden benachrichtigt, wenn der Export fertig ist.`
          : result.message,
      });
      onSuccess?.(result, 'export');
    },
    onError: (error: Error) => handleError(error, 'export'),
  });

  // Categorize mutation
  const categorizeMutation = useMutation({
    mutationFn: (category: string) => bulkCategorizeDocuments(selectedIds, category),
    onMutate: () => startBatch('Kategorisieren', selectedCount),
    onSuccess: (result) =>
      handleResult(result, 'categorize', `${result.processed} Dokumente kategorisiert`),
    onError: (error: Error) => handleError(error, 'categorize'),
  });

  // =============================================================================
  // Operation Wrappers
  // =============================================================================

  const addTags = useCallback(
    async (tags: string[]) => {
      if (selectedCount === 0) {
        toast.warning('Keine Dokumente ausgewählt');
        return;
      }
      await addTagsMutation.mutateAsync(tags);
    },
    [selectedCount, addTagsMutation]
  );

  const removeTags = useCallback(
    async (tags: string[]) => {
      if (selectedCount === 0) {
        toast.warning('Keine Dokumente ausgewählt');
        return;
      }
      await removeTagsMutation.mutateAsync(tags);
    },
    [selectedCount, removeTagsMutation]
  );

  const setTags = useCallback(
    async (tags: string[]) => {
      if (selectedCount === 0) {
        toast.warning('Keine Dokumente ausgewählt');
        return;
      }
      await setTagsMutation.mutateAsync(tags);
    },
    [selectedCount, setTagsMutation]
  );

  const moveToFolder = useCallback(
    async (folderId: string) => {
      if (selectedCount === 0) {
        toast.warning('Keine Dokumente ausgewählt');
        return;
      }
      await moveMutation.mutateAsync(folderId);
    },
    [selectedCount, moveMutation]
  );

  const deleteDocuments = useCallback(
    async (reason?: string) => {
      if (selectedCount === 0) {
        toast.warning('Keine Dokumente ausgewählt');
        return;
      }
      await deleteMutation.mutateAsync(reason);
    },
    [selectedCount, deleteMutation]
  );

  const exportDocuments = useCallback(
    async (format: ExportFormat = 'zip', includeMetadata: boolean = true) => {
      if (selectedCount === 0) {
        toast.warning('Keine Dokumente ausgewählt');
        return;
      }
      await exportMutation.mutateAsync({ format, includeMetadata });
    },
    [selectedCount, exportMutation]
  );

  const categorize = useCallback(
    async (category: string) => {
      if (selectedCount === 0) {
        toast.warning('Keine Dokumente ausgewählt');
        return;
      }
      await categorizeMutation.mutateAsync(category);
    },
    [selectedCount, categorizeMutation]
  );

  // Loading states
  const isTagging =
    addTagsMutation.isPending || removeTagsMutation.isPending || setTagsMutation.isPending;
  const isMoving = moveMutation.isPending;
  const isDeleting = deleteMutation.isPending;
  const isExporting = exportMutation.isPending;
  const isCategorizing = categorizeMutation.isPending;
  const isAnyOperationPending =
    isTagging || isMoving || isDeleting || isExporting || isCategorizing;

  return {
    // Selection
    selectedIds,
    selectedCount,
    isSelected,
    toggleSelection,
    selectAll,
    clearSelection,
    selectRange,

    // Progress
    progress,

    // Operations
    addTags,
    removeTags,
    setTags,
    moveToFolder,
    deleteDocuments,
    exportDocuments,
    categorize,

    // Loading states
    isTagging,
    isMoving,
    isDeleting,
    isExporting,
    isCategorizing,
    isAnyOperationPending,
  };
}
