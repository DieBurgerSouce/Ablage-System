/**
 * Validation Queue React Query Hooks
 *
 * TanStack Query Hooks für das Enterprise-Grade Validierungs-Queue-System.
 * Bietet caching, optimistic updates und automatisches refetching.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  validationQueueApi,
  validationQueryKeys,
  type ListQueueParams,
} from '../api/validation-queue-api';
import type {
  ValidationQueueItem,
  ValidationQueueItemDetail,
  ValidationQueueItemCreate,
  ValidationQueueItemUpdate,
  ValidationQueueItemAssign,
  ValidationQueueItemApprove,
  ValidationQueueItemReject,
  ValidationFieldReview,
  ValidationFieldUpdate,
  ValidationRule,
  ValidationRuleCreate,
  ValidationRuleUpdate,
  ValidationSampleConfig,
  ValidationSampleConfigUpdate,
  BatchApproveRequest,
  BatchRejectRequest,
  BatchAssignRequest,
  ValidationStatus,
} from '../types/validation-queue.types';

// ==================== Queue Queries ====================

/**
 * Hook für die Validierungs-Queue mit Filtern und Paginierung.
 */
export function useValidationQueue(params: ListQueueParams = {}) {
  return useQuery({
    queryKey: validationQueryKeys.queue(params),
    queryFn: () => validationQueueApi.listQueue(params),
    staleTime: 30_000, // 30 Sekunden
  });
}

/**
 * Hook für Queue-Statistiken.
 */
export function useQueueStats() {
  return useQuery({
    queryKey: validationQueryKeys.queueStats(),
    queryFn: validationQueueApi.getQueueStats,
    staleTime: 60_000, // 1 Minute
    refetchInterval: 60_000, // Auto-refresh jede Minute
    refetchIntervalInBackground: false, // Nur im Vordergrund aktualisieren
  });
}

/**
 * Hook für die dem aktuellen Benutzer zugewiesenen Items.
 * Nutzt Lazy Loading - wird nur geladen wenn `enabled` true ist.
 */
export function useMyAssignedItems(
  status?: ValidationStatus,
  limit = 50,
  offset = 0,
  enabled = true
) {
  return useQuery({
    queryKey: [...validationQueryKeys.myItems(), status, limit, offset],
    queryFn: () => validationQueueApi.getMyItems(status, limit, offset),
    staleTime: 30_000,
    enabled, // Lazy Loading: Nur laden wenn Tab aktiv
  });
}

/**
 * Hook für ein einzelnes Queue-Item mit Details.
 */
export function useQueueItem(itemId: string | undefined) {
  return useQuery({
    queryKey: validationQueryKeys.queueItem(itemId!),
    queryFn: () => validationQueueApi.getQueueItem(itemId!),
    enabled: !!itemId,
    staleTime: 30_000,
  });
}

/**
 * Hook für Feld-Reviews eines Queue-Items.
 */
export function useQueueItemFields(itemId: string | undefined) {
  return useQuery({
    queryKey: validationQueryKeys.fields(itemId!),
    queryFn: () => validationQueueApi.getFields(itemId!),
    enabled: !!itemId,
    staleTime: 30_000,
  });
}

/**
 * Hook für Feld-Statistiken.
 */
export function useFieldStats(itemId: string | undefined) {
  return useQuery({
    queryKey: validationQueryKeys.fieldStats(itemId!),
    queryFn: () => validationQueueApi.getFieldStats(itemId!),
    enabled: !!itemId,
    staleTime: 60_000,
  });
}

// ==================== Queue Mutations ====================

/**
 * Hook zum Erstellen eines Queue-Items.
 */
export function useCreateQueueItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ValidationQueueItemCreate) => validationQueueApi.createQueueItem(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.all });
      toast.success('Dokument zur Validierung hinzugefügt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Hook zum Aktualisieren eines Queue-Items.
 */
export function useUpdateQueueItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ itemId, data }: { itemId: string; data: ValidationQueueItemUpdate }) =>
      validationQueueApi.updateQueueItem(itemId, data),
    onSuccess: (_, { itemId }) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queueItem(itemId) });
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queue() });
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Hook zum Löschen eines Queue-Items.
 */
export function useDeleteQueueItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itemId: string) => validationQueueApi.deleteQueueItem(itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.all });
      toast.success('Item gelöscht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// ==================== Assignment Mutations ====================

/**
 * Hook zum Zuweisen eines Queue-Items.
 */
export function useAssignQueueItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ itemId, data }: { itemId: string; data: ValidationQueueItemAssign }) =>
      validationQueueApi.assignItem(itemId, data),
    onSuccess: (_, { itemId }) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queueItem(itemId) });
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queue() });
      toast.success('Item zugewiesen');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Hook zum Entfernen der Zuweisung.
 */
export function useUnassignQueueItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itemId: string) => validationQueueApi.unassignItem(itemId),
    onSuccess: (_, itemId) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queueItem(itemId) });
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queue() });
      toast.success('Zuweisung entfernt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// ==================== Approval/Rejection Mutations ====================

/**
 * Hook zum Genehmigen eines Queue-Items.
 */
export function useApproveQueueItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ itemId, data }: { itemId: string; data?: ValidationQueueItemApprove }) =>
      validationQueueApi.approveItem(itemId, data || {}),
    onSuccess: (_, { itemId }) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queueItem(itemId) });
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queue() });
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queueStats() });
      toast.success('Item genehmigt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Hook zum Ablehnen eines Queue-Items.
 */
export function useRejectQueueItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ itemId, data }: { itemId: string; data: ValidationQueueItemReject }) =>
      validationQueueApi.rejectItem(itemId, data),
    onSuccess: (_, { itemId }) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queueItem(itemId) });
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queue() });
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queueStats() });
      toast.success('Item abgelehnt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// ==================== Batch Mutations with Optimistic Updates ====================

/**
 * Hook für Batch-Genehmigung mit Optimistic Updates.
 * Aktualisiert die UI sofort und rollt bei Fehler zurück.
 */
export function useBatchApprove() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: BatchApproveRequest) => validationQueueApi.batchApprove(data),
    onMutate: async (data) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: validationQueryKeys.queue() });

      // Snapshot previous value for rollback
      const previousQueueData = queryClient.getQueriesData({ queryKey: validationQueryKeys.queue() });

      // Optimistically update queue items to approved status
      queryClient.setQueriesData(
        { queryKey: validationQueryKeys.queue() },
        (old: { items: ValidationQueueItem[]; total: number } | undefined) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map((item) =>
              data.item_ids.includes(item.id)
                ? { ...item, status: 'approved' as ValidationStatus }
                : item
            ),
          };
        }
      );

      // Return context with snapshot for rollback
      return { previousQueueData };
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.all });
      toast.success(`${result.success_count} Items genehmigt`);
      if (result.failure_count > 0) {
        toast.warning(`${result.failure_count} Items konnten nicht genehmigt werden`);
      }
    },
    onError: (error: Error, _data, context) => {
      // Rollback on error
      if (context?.previousQueueData) {
        context.previousQueueData.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
      toast.error(`Fehler: ${error.message}`);
    },
    onSettled: () => {
      // Always refetch after error or success to sync with server
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queue() });
    },
  });
}

/**
 * Hook für Batch-Ablehnung mit Optimistic Updates.
 */
export function useBatchReject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: BatchRejectRequest) => validationQueueApi.batchReject(data),
    onMutate: async (data) => {
      await queryClient.cancelQueries({ queryKey: validationQueryKeys.queue() });

      const previousQueueData = queryClient.getQueriesData({ queryKey: validationQueryKeys.queue() });

      // Optimistically update queue items to rejected status
      queryClient.setQueriesData(
        { queryKey: validationQueryKeys.queue() },
        (old: { items: ValidationQueueItem[]; total: number } | undefined) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map((item) =>
              data.item_ids.includes(item.id)
                ? { ...item, status: 'rejected' as ValidationStatus }
                : item
            ),
          };
        }
      );

      return { previousQueueData };
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.all });
      toast.success(`${result.success_count} Items abgelehnt`);
      if (result.failure_count > 0) {
        toast.warning(`${result.failure_count} Items konnten nicht abgelehnt werden`);
      }
    },
    onError: (error: Error, _data, context) => {
      if (context?.previousQueueData) {
        context.previousQueueData.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
      toast.error(`Fehler: ${error.message}`);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queue() });
    },
  });
}

/**
 * Hook für Batch-Zuweisung mit Optimistic Updates.
 */
export function useBatchAssign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: BatchAssignRequest) => validationQueueApi.batchAssign(data),
    onMutate: async (data) => {
      await queryClient.cancelQueries({ queryKey: validationQueryKeys.queue() });

      const previousQueueData = queryClient.getQueriesData({ queryKey: validationQueryKeys.queue() });

      // Optimistically update assigned_to field
      queryClient.setQueriesData(
        { queryKey: validationQueryKeys.queue() },
        (old: { items: ValidationQueueItem[]; total: number } | undefined) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map((item) =>
              data.item_ids.includes(item.id)
                ? { ...item, assigned_to: data.editor_id, status: 'in_progress' as ValidationStatus }
                : item
            ),
          };
        }
      );

      return { previousQueueData };
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.all });
      toast.success(`${result.success_count} Items zugewiesen`);
      if (result.failure_count > 0) {
        toast.warning(`${result.failure_count} Items konnten nicht zugewiesen werden`);
      }
    },
    onError: (error: Error, _data, context) => {
      if (context?.previousQueueData) {
        context.previousQueueData.forEach(([queryKey, data]) => {
          queryClient.setQueryData(queryKey, data);
        });
      }
      toast.error(`Fehler: ${error.message}`);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queue() });
    },
  });
}

// ==================== Field Mutations ====================

/**
 * Hook zum Aktualisieren eines Feldwerts.
 */
export function useUpdateField() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      itemId,
      fieldId,
      data,
    }: {
      itemId: string;
      fieldId: string;
      data: ValidationFieldUpdate;
    }) => validationQueueApi.updateField(itemId, fieldId, data),
    onSuccess: (_, { itemId }) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.fields(itemId) });
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.queueItem(itemId) });
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Hook zum Validieren eines einzelnen Felds.
 */
export function useValidateField() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ itemId, fieldId }: { itemId: string; fieldId: string }) =>
      validationQueueApi.validateField(itemId, fieldId),
    onSuccess: (result, { itemId }) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.fields(itemId) });
      if (result.is_valid) {
        toast.success('Feld validiert');
      } else {
        toast.warning('Feld hat Validierungsfehler');
      }
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Hook zum Validieren aller Felder.
 */
export function useValidateAllFields() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (itemId: string) => validationQueueApi.validateAllFields(itemId),
    onSuccess: (results, itemId) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.fields(itemId) });
      const validCount = results.filter((r) => r.is_valid).length;
      const invalidCount = results.length - validCount;
      if (invalidCount === 0) {
        toast.success('Alle Felder validiert');
      } else {
        toast.warning(`${invalidCount} von ${results.length} Feldern haben Fehler`);
      }
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// ==================== Rules Queries & Mutations ====================

/**
 * Hook für Validierungsregeln.
 */
export function useValidationRules(includeInactive = false) {
  return useQuery({
    queryKey: [...validationQueryKeys.rules(), includeInactive],
    queryFn: () => validationQueueApi.listRules(includeInactive),
    staleTime: 60_000,
  });
}

/**
 * Hook für eine einzelne Regel.
 */
export function useValidationRule(ruleId: string | undefined) {
  return useQuery({
    queryKey: validationQueryKeys.rule(ruleId!),
    queryFn: () => validationQueueApi.getRule(ruleId!),
    enabled: !!ruleId,
    staleTime: 60_000,
  });
}

/**
 * Hook zum Erstellen einer Regel.
 */
export function useCreateRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ValidationRuleCreate) => validationQueueApi.createRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.rules() });
      toast.success('Regel erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Hook zum Aktualisieren einer Regel.
 */
export function useUpdateRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ ruleId, data }: { ruleId: string; data: ValidationRuleUpdate }) =>
      validationQueueApi.updateRule(ruleId, data),
    onSuccess: (_, { ruleId }) => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.rule(ruleId) });
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.rules() });
      toast.success('Regel aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

/**
 * Hook zum Löschen einer Regel.
 */
export function useDeleteRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ruleId: string) => validationQueueApi.deleteRule(ruleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.rules() });
      toast.success('Regel gelöscht');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// ==================== Sample Config ====================

/**
 * Hook für die Stichproben-Konfiguration.
 */
export function useSampleConfig() {
  return useQuery({
    queryKey: validationQueryKeys.sampleConfig(),
    queryFn: validationQueueApi.getSampleConfig,
    staleTime: 60_000,
  });
}

/**
 * Hook zum Aktualisieren der Stichproben-Konfiguration.
 */
export function useUpdateSampleConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ValidationSampleConfigUpdate) =>
      validationQueueApi.updateSampleConfig('default', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.sampleConfig() });
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}

// ==================== Analytics Queries ====================

/**
 * Hook für Analytics-Übersicht.
 */
export function useAnalyticsOverview(dateFrom?: string, dateTo?: string) {
  return useQuery({
    queryKey: validationQueryKeys.analyticsOverview(dateFrom, dateTo),
    queryFn: () => validationQueueApi.getOverview(dateFrom, dateTo),
    staleTime: 60_000,
  });
}

/**
 * Hook für Editor-Statistiken.
 */
export function useEditorStats(dateFrom?: string, dateTo?: string) {
  return useQuery({
    queryKey: validationQueryKeys.editorStats(dateFrom, dateTo),
    queryFn: () => validationQueueApi.getEditorStats(dateFrom, dateTo),
    staleTime: 60_000,
  });
}

/**
 * Hook für Trend-Daten.
 */
export function useTrends(days = 30, groupBy: 'day' | 'week' | 'month' = 'day') {
  return useQuery({
    queryKey: validationQueryKeys.trends(days, groupBy),
    queryFn: () => validationQueueApi.getTrends(days, groupBy),
    staleTime: 60_000,
  });
}

/**
 * Hook für Dokumenttyp-Statistiken.
 */
export function useDocumentTypeStats() {
  return useQuery({
    queryKey: validationQueryKeys.documentTypes(),
    queryFn: validationQueueApi.getDocumentTypeStats,
    staleTime: 60_000,
  });
}

/**
 * Hook für Confidence-Verteilung.
 */
export function useConfidenceDistribution() {
  return useQuery({
    queryKey: validationQueryKeys.confidenceDistribution(),
    queryFn: validationQueueApi.getConfidenceDistribution,
    staleTime: 60_000,
  });
}

// ==================== Document Integration ====================

/**
 * Hook zum Hinzufügen eines Dokuments zur Validierungswarteschlange.
 */
export function useQueueDocumentForValidation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      documentId,
      priority,
      notes,
    }: {
      documentId: string;
      priority?: number;
      notes?: string;
    }) => validationQueueApi.queueDocument(documentId, priority, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.all });
      toast.success('Dokument zur Validierung hinzugefügt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler: ${error.message}`);
    },
  });
}
