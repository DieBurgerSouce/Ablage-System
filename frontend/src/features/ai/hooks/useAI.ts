/**
 * AI Autonomy React Query Hooks
 *
 * React Query Hooks fuer AI Autonomy Features.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listDecisions,
  getDecision,
  reviewDecision,
  listThresholds,
  updateThreshold,
  categorizeDocument,
  getCategorySuggestions,
  findDocumentMatches,
  checkDocumentAnomalies,
  checkDocumentDuplicates,
  getAccuracyStats,
  getLearningProgress,
  getThresholdSuggestions,
  applyThresholdSuggestion,
  getPendingReviewCount,
  ReviewRequest,
  ThresholdUpdateRequest,
} from '../api/ai-api';

// =============================================================================
// Query Keys
// =============================================================================

export const aiQueryKeys = {
  all: ['ai'] as const,
  decisions: () => [...aiQueryKeys.all, 'decisions'] as const,
  decisionsFiltered: (filters: Record<string, unknown>) =>
    [...aiQueryKeys.decisions(), filters] as const,
  decision: (id: string) => [...aiQueryKeys.decisions(), id] as const,
  thresholds: () => [...aiQueryKeys.all, 'thresholds'] as const,
  categorySuggestions: (documentId: string) =>
    [...aiQueryKeys.all, 'category-suggestions', documentId] as const,
  matches: (documentId: string) => [...aiQueryKeys.all, 'matches', documentId] as const,
  anomalies: (documentId: string) => [...aiQueryKeys.all, 'anomalies', documentId] as const,
  duplicates: (documentId: string) => [...aiQueryKeys.all, 'duplicates', documentId] as const,
  accuracyStats: (days: number) => [...aiQueryKeys.all, 'accuracy-stats', days] as const,
  learningProgress: (days: number) => [...aiQueryKeys.all, 'learning-progress', days] as const,
  thresholdSuggestions: (days: number) =>
    [...aiQueryKeys.all, 'threshold-suggestions', days] as const,
  pendingReviewCount: () => [...aiQueryKeys.all, 'pending-review-count'] as const,
};

// =============================================================================
// Decision Hooks
// =============================================================================

export function useDecisions(params?: {
  decision_type?: string;
  requires_review?: boolean;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: aiQueryKeys.decisionsFiltered(params ?? {}),
    queryFn: () => listDecisions(params),
    staleTime: 30_000, // 30 Sekunden
  });
}

export function useDecision(decisionId: string) {
  return useQuery({
    queryKey: aiQueryKeys.decision(decisionId),
    queryFn: () => getDecision(decisionId),
    enabled: !!decisionId,
  });
}

export function useReviewDecision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ decisionId, request }: { decisionId: string; request: ReviewRequest }) =>
      reviewDecision(decisionId, request),
    onSuccess: (_data, variables) => {
      // Invalidiere spezifische Entscheidung
      queryClient.invalidateQueries({
        queryKey: aiQueryKeys.decision(variables.decisionId),
      });
      // Invalidiere Entscheidungs-Listen
      queryClient.invalidateQueries({ queryKey: aiQueryKeys.decisions() });
      // Invalidiere Pending-Count
      queryClient.invalidateQueries({ queryKey: aiQueryKeys.pendingReviewCount() });
    },
  });
}

export function usePendingReviewCount() {
  return useQuery({
    queryKey: aiQueryKeys.pendingReviewCount(),
    queryFn: getPendingReviewCount,
    staleTime: 60_000, // 1 Minute
    refetchInterval: 60_000, // Polling alle 60 Sekunden
  });
}

// =============================================================================
// Threshold Hooks
// =============================================================================

export function useThresholds() {
  return useQuery({
    queryKey: aiQueryKeys.thresholds(),
    queryFn: listThresholds,
    staleTime: 300_000, // 5 Minuten
  });
}

export function useUpdateThreshold() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      decisionType,
      request,
    }: {
      decisionType: string;
      request: ThresholdUpdateRequest;
    }) => updateThreshold(decisionType, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiQueryKeys.thresholds() });
    },
  });
}

// =============================================================================
// Document AI Hooks
// =============================================================================

export function useCategorizeDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ documentId, autoApply = true }: { documentId: string; autoApply?: boolean }) =>
      categorizeDocument(documentId, autoApply),
    onSuccess: (_data, variables) => {
      // Invalidiere Kategorie-Vorschlaege
      queryClient.invalidateQueries({
        queryKey: aiQueryKeys.categorySuggestions(variables.documentId),
      });
      // Invalidiere Entscheidungen
      queryClient.invalidateQueries({ queryKey: aiQueryKeys.decisions() });
    },
  });
}

export function useCategorySuggestions(documentId: string) {
  return useQuery({
    queryKey: aiQueryKeys.categorySuggestions(documentId),
    queryFn: () => getCategorySuggestions(documentId),
    enabled: !!documentId,
    staleTime: 60_000,
  });
}

export function useDocumentMatches(documentId: string, limit = 10) {
  return useQuery({
    queryKey: aiQueryKeys.matches(documentId),
    queryFn: () => findDocumentMatches(documentId, limit),
    enabled: !!documentId,
    staleTime: 60_000,
  });
}

export function useDocumentAnomalies(documentId: string) {
  return useQuery({
    queryKey: aiQueryKeys.anomalies(documentId),
    queryFn: () => checkDocumentAnomalies(documentId),
    enabled: !!documentId,
    staleTime: 120_000, // 2 Minuten
  });
}

export function useDocumentDuplicates(documentId: string, includeNear = true) {
  return useQuery({
    queryKey: aiQueryKeys.duplicates(documentId),
    queryFn: () => checkDocumentDuplicates(documentId, includeNear),
    enabled: !!documentId,
    staleTime: 120_000,
  });
}

// =============================================================================
// Statistics & Learning Hooks
// =============================================================================

export function useAccuracyStats(days = 30) {
  return useQuery({
    queryKey: aiQueryKeys.accuracyStats(days),
    queryFn: () => getAccuracyStats(days),
    staleTime: 300_000, // 5 Minuten
  });
}

export function useLearningProgress(days = 30) {
  return useQuery({
    queryKey: aiQueryKeys.learningProgress(days),
    queryFn: () => getLearningProgress(days),
    staleTime: 300_000,
  });
}

export function useThresholdSuggestions(days = 30) {
  return useQuery({
    queryKey: aiQueryKeys.thresholdSuggestions(days),
    queryFn: () => getThresholdSuggestions(days),
    staleTime: 300_000,
  });
}

export function useApplyThresholdSuggestion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (decisionType: string) => applyThresholdSuggestion(decisionType),
    onSuccess: () => {
      // Invalidiere Thresholds und Suggestions
      queryClient.invalidateQueries({ queryKey: aiQueryKeys.thresholds() });
      queryClient.invalidateQueries({ queryKey: aiQueryKeys.thresholdSuggestions(30) });
    },
  });
}
