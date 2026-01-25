/**
 * Smart Queue Hooks
 *
 * Hooks fuer intelligente OCR-Warteschlange mit Priorisierung.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

// =============================================================================
// Types
// =============================================================================

export type PriorityReason =
  | 'skonto_deadline'
  | 'dunning_notice'
  | 'manual_high'
  | 'urgent_flag'
  | 'vip_customer'
  | 'high_amount'
  | 'default';

export type QueueStatus = 'waiting' | 'processing' | 'completed' | 'failed' | 'paused';

export interface QueueItem {
  id: string;
  document_id: string;
  document_name: string;
  document_type: string | null;
  priority: number;
  priority_reasons: PriorityReason[];
  status: QueueStatus;
  backend: string | null;
  created_at: string;
  started_at: string | null;
  estimated_completion: string | null;
  skonto_deadline: string | null;
  detected_amount: number | null;
  entity_name: string | null;
  is_dunning: boolean;
  wait_time_seconds: number;
}

export interface QueueStats {
  total_waiting: number;
  total_processing: number;
  total_completed_today: number;
  total_failed_today: number;
  avg_wait_time_seconds: number;
  avg_processing_time_seconds: number;
  priority_distribution: Record<string, number>;
  skonto_at_risk: number;
  dunning_pending: number;
}

export interface PriorityRule {
  id: string;
  name: string;
  description: string;
  condition_type: 'skonto_days' | 'amount_threshold' | 'entity_type' | 'document_type' | 'custom';
  condition_value: string;
  priority_boost: number;
  enabled: boolean;
  created_at: string;
}

// =============================================================================
// Query Keys
// =============================================================================

export const smartQueueKeys = {
  all: ['smart-queue'] as const,
  stats: () => [...smartQueueKeys.all, 'stats'] as const,
  items: (status?: QueueStatus) => [...smartQueueKeys.all, 'items', status] as const,
  rules: () => [...smartQueueKeys.all, 'rules'] as const,
  predictions: () => [...smartQueueKeys.all, 'predictions'] as const,
};

// =============================================================================
// Hooks
// =============================================================================

/**
 * Hook zum Abrufen der Queue-Statistiken
 */
export function useQueueStats() {
  return useQuery({
    queryKey: smartQueueKeys.stats(),
    queryFn: async () => {
      const response = await api.get<QueueStats>('/api/v1/ocr/queue/stats');
      return response.data;
    },
    staleTime: 10_000, // 10 Sekunden
    refetchInterval: 30_000, // Auto-refresh alle 30s
  });
}

/**
 * Hook zum Abrufen der Queue-Items
 */
export function useQueueItems(status?: QueueStatus, limit = 50) {
  return useQuery({
    queryKey: smartQueueKeys.items(status),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (status) params.set('status', status);
      params.set('limit', String(limit));

      const response = await api.get<{ items: QueueItem[]; total: number }>(
        `/api/v1/ocr/queue/items?${params.toString()}`
      );
      return response.data;
    },
    staleTime: 10_000,
    refetchInterval: 30_000,
  });
}

/**
 * Hook zum Abrufen der Priorisierungs-Regeln
 */
export function usePriorityRules() {
  return useQuery({
    queryKey: smartQueueKeys.rules(),
    queryFn: async () => {
      const response = await api.get<PriorityRule[]>('/api/v1/ocr/queue/rules');
      return response.data;
    },
    staleTime: 300_000, // 5 Minuten
  });
}

/**
 * Hook zum Aendern der Prioritaet eines Items
 */
export function useChangePriority() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      documentId,
      priority,
      reason,
    }: {
      documentId: string;
      priority: number;
      reason?: string;
    }) => {
      const response = await api.patch<QueueItem>(
        `/api/v1/ocr/queue/items/${documentId}/priority`,
        { priority, reason }
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: smartQueueKeys.items() });
      queryClient.invalidateQueries({ queryKey: smartQueueKeys.stats() });
    },
  });
}

/**
 * Hook zum Pausieren/Fortsetzen eines Items
 */
export function usePauseResumeItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      documentId,
      action,
    }: {
      documentId: string;
      action: 'pause' | 'resume';
    }) => {
      const response = await api.post<QueueItem>(
        `/api/v1/ocr/queue/items/${documentId}/${action}`
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: smartQueueKeys.items() });
    },
  });
}

/**
 * Hook zum Erstellen/Aktualisieren einer Priorisierungs-Regel
 */
export function useSavePriorityRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (rule: Omit<PriorityRule, 'id' | 'created_at'> & { id?: string }) => {
      if (rule.id) {
        const response = await api.patch<PriorityRule>(
          `/api/v1/ocr/queue/rules/${rule.id}`,
          rule
        );
        return response.data;
      } else {
        const response = await api.post<PriorityRule>('/api/v1/ocr/queue/rules', rule);
        return response.data;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: smartQueueKeys.rules() });
    },
  });
}

/**
 * Hook zum Loeschen einer Priorisierungs-Regel
 */
export function useDeletePriorityRule() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (ruleId: string) => {
      await api.delete(`/api/v1/ocr/queue/rules/${ruleId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: smartQueueKeys.rules() });
    },
  });
}

/**
 * Hook fuer Neuberechnung aller Prioritaeten
 */
export function useRecalculatePriorities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<{ recalculated: number }>(
        '/api/v1/ocr/queue/recalculate'
      );
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: smartQueueKeys.all });
    },
  });
}
