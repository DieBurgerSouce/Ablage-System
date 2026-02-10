/**
 * AI Admin React Query Hooks
 *
 * Custom Hooks fuer AI Admin mit TanStack Query.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  listThresholds,
  updateThreshold,
  listDecisions,
  getDecision,
  reviewDecision,
  getPendingReviewCount,
  getAccuracyStats,
  getLearningProgress,
  getThresholdSuggestions,
  applyThresholdSuggestion,
  aiAdminKeys,
} from '../api/ai-admin-api';
import type {
  ThresholdUpdateRequest,
  ReviewRequest,
  DecisionType,
} from '../types';

// =============================================================================
// Threshold Hooks
// =============================================================================

export function useThresholds() {
  return useQuery({
    queryKey: aiAdminKeys.thresholds(),
    queryFn: listThresholds,
  });
}

export function useUpdateThreshold() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      decisionType,
      data,
    }: {
      decisionType: DecisionType;
      data: ThresholdUpdateRequest;
    }) => updateThreshold(decisionType, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiAdminKeys.thresholds() });
      toast.success('Schwellenwerte aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

// =============================================================================
// Decision Hooks
// =============================================================================

export function useDecisions(params: {
  decision_type?: DecisionType;
  requires_review?: boolean;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: aiAdminKeys.decisions(params),
    queryFn: () => listDecisions(params),
    refetchInterval: 30000, // Alle 30 Sekunden aktualisieren
  });
}

export function useDecision(decisionId: string) {
  return useQuery({
    queryKey: aiAdminKeys.decision(decisionId),
    queryFn: () => getDecision(decisionId),
    enabled: !!decisionId,
  });
}

export function useReviewDecision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      decisionId,
      request,
    }: {
      decisionId: string;
      request: ReviewRequest;
    }) => reviewDecision(decisionId, request),
    onSuccess: (_, { request }) => {
      queryClient.invalidateQueries({ queryKey: aiAdminKeys.decisions() });
      queryClient.invalidateQueries({ queryKey: aiAdminKeys.pendingCount() });
      queryClient.invalidateQueries({ queryKey: aiAdminKeys.accuracyStats(30) });

      const actionText =
        request.action === 'approved'
          ? 'genehmigt'
          : request.action === 'rejected'
            ? 'abgelehnt'
            : 'angepasst';
      toast.success(`Entscheidung ${actionText}`);
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Review: ${error.message}`);
    },
  });
}

export function usePendingReviewCount() {
  return useQuery({
    queryKey: aiAdminKeys.pendingCount(),
    queryFn: getPendingReviewCount,
    refetchInterval: 30000, // Alle 30 Sekunden aktualisieren
  });
}

// =============================================================================
// Statistics Hooks
// =============================================================================

export function useAccuracyStats(days: number = 30) {
  return useQuery({
    queryKey: aiAdminKeys.accuracyStats(days),
    queryFn: () => getAccuracyStats(days),
    refetchInterval: 60000, // Jede Minute aktualisieren
  });
}

export function useLearningProgress(days: number = 30) {
  return useQuery({
    queryKey: aiAdminKeys.learningProgress(days),
    queryFn: () => getLearningProgress(days),
    refetchInterval: 60000, // Jede Minute aktualisieren
  });
}

export function useThresholdSuggestions(days: number = 30) {
  return useQuery({
    queryKey: aiAdminKeys.thresholdSuggestions(days),
    queryFn: () => getThresholdSuggestions(days),
    refetchInterval: 60000, // Jede Minute aktualisieren
  });
}

export function useApplyThresholdSuggestion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (decisionType: DecisionType) =>
      applyThresholdSuggestion(decisionType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiAdminKeys.thresholds() });
      queryClient.invalidateQueries({ queryKey: aiAdminKeys.thresholdSuggestions(30) });
      toast.success('Schwellenwert-Vorschlag angewendet');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Anwenden: ${error.message}`);
    },
  });
}
