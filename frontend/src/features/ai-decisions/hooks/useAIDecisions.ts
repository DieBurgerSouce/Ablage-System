/**
 * AI Decision Review - React Query Hooks
 *
 * Hooks fuer ML/AI Entscheidungen, Drift Detection,
 * SHAP Erklaerungen und A/B Testing.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as aiApi from '../api/ai-api';
import type {
  AIDecisionFilters,
  CreateExperimentRequest,
  ConfidenceThresholds,
} from '../types/ai-types';

// =============================================================================
// Query Keys
// =============================================================================

export const aiKeys = {
  all: ['ai'] as const,
  drift: () => [...aiKeys.all, 'drift'] as const,
  driftStatus: () => [...aiKeys.drift(), 'status'] as const,
  driftHistory: (limit?: number) => [...aiKeys.drift(), 'history', limit] as const,
  explain: () => [...aiKeys.all, 'explain'] as const,
  explanation: (docId: string) => [...aiKeys.explain(), docId] as const,
  featureImportance: () => [...aiKeys.explain(), 'importance'] as const,
  experiments: () => [...aiKeys.all, 'experiments'] as const,
  experimentsList: (status?: string) => [...aiKeys.experiments(), 'list', status] as const,
  experiment: (id: string) => [...aiKeys.experiments(), id] as const,
  metrics: () => [...aiKeys.all, 'metrics'] as const,
  decisions: () => [...aiKeys.all, 'decisions'] as const,
  decisionsList: (filters?: AIDecisionFilters) => [...aiKeys.decisions(), 'list', filters] as const,
  decisionStats: () => [...aiKeys.decisions(), 'stats'] as const,
  learning: () => [...aiKeys.all, 'learning'] as const,
  learningStats: () => [...aiKeys.learning(), 'stats'] as const,
  thresholds: () => [...aiKeys.all, 'thresholds'] as const,
};

// =============================================================================
// Drift Detection Hooks
// =============================================================================

export function useDriftStatus() {
  return useQuery({
    queryKey: aiKeys.driftStatus(),
    queryFn: aiApi.getDriftStatus,
    staleTime: 60000, // 1 Minute
    refetchInterval: 60000,
  });
}

export function useDriftHistory(limit = 10) {
  return useQuery({
    queryKey: aiKeys.driftHistory(limit),
    queryFn: () => aiApi.getDriftHistory(limit),
    staleTime: 120000, // 2 Minuten
  });
}

export function useRunDriftDetection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: aiApi.runDriftDetection,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.drift() });
    },
  });
}

export function useResetDriftReference() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: aiApi.resetDriftReference,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.drift() });
    },
  });
}

// =============================================================================
// SHAP Explainability Hooks
// =============================================================================

export function useRoutingExplanation(documentId: string, enabled = true) {
  return useQuery({
    queryKey: aiKeys.explanation(documentId),
    queryFn: () => aiApi.getRoutingExplanation(documentId),
    enabled: enabled && !!documentId,
    staleTime: 300000, // 5 Minuten
  });
}

export function useGlobalFeatureImportance() {
  return useQuery({
    queryKey: aiKeys.featureImportance(),
    queryFn: aiApi.getGlobalFeatureImportance,
    staleTime: 300000, // 5 Minuten
  });
}

// =============================================================================
// A/B Testing Hooks
// =============================================================================

export function useExperiments(status?: string) {
  return useQuery({
    queryKey: aiKeys.experimentsList(status),
    queryFn: () => aiApi.listExperiments(status),
    staleTime: 30000, // 30 Sekunden
  });
}

export function useExperiment(experimentId: string, enabled = true) {
  return useQuery({
    queryKey: aiKeys.experiment(experimentId),
    queryFn: () => aiApi.getExperiment(experimentId),
    enabled: enabled && !!experimentId,
    staleTime: 30000,
    refetchInterval: 30000, // Live-Updates fuer laufende Experimente
  });
}

export function useCreateExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateExperimentRequest) => aiApi.createExperiment(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.experiments() });
    },
  });
}

export function useStartExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (experimentId: string) => aiApi.startExperiment(experimentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.experiments() });
    },
  });
}

export function useConcludeExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (experimentId: string) => aiApi.concludeExperiment(experimentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.experiments() });
    },
  });
}

// =============================================================================
// Metrics Hooks
// =============================================================================

export function useMetricsSummary() {
  return useQuery({
    queryKey: aiKeys.metrics(),
    queryFn: aiApi.getMetricsSummary,
    staleTime: 30000,
    refetchInterval: 30000,
  });
}

// =============================================================================
// AI Decision Review Hooks
// =============================================================================

export function useAIDecisions(filters?: AIDecisionFilters, page = 1, pageSize = 20) {
  return useQuery({
    queryKey: aiKeys.decisionsList(filters),
    queryFn: () => aiApi.getAIDecisions(filters, page, pageSize),
    staleTime: 10000, // 10 Sekunden
  });
}

export function useAIDecisionStats() {
  return useQuery({
    queryKey: aiKeys.decisionStats(),
    queryFn: aiApi.getAIDecisionStats,
    staleTime: 30000,
  });
}

export function useReviewAIDecision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      decisionId,
      outcome,
      correction,
    }: {
      decisionId: string;
      outcome: 'approved' | 'corrected' | 'rejected';
      correction?: string;
    }) => aiApi.reviewAIDecision(decisionId, outcome, correction),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.decisions() });
    },
  });
}

// =============================================================================
// Learning Stats Hooks
// =============================================================================

export function useLearningStats() {
  return useQuery({
    queryKey: aiKeys.learningStats(),
    queryFn: aiApi.getLearningStats,
    staleTime: 60000, // 1 Minute
  });
}

// =============================================================================
// Threshold Settings Hooks
// =============================================================================

export function useConfidenceThresholds() {
  return useQuery({
    queryKey: aiKeys.thresholds(),
    queryFn: aiApi.getConfidenceThresholds,
    staleTime: 300000, // 5 Minuten
  });
}

export function useUpdateConfidenceThresholds() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (thresholds: Partial<ConfidenceThresholds>) =>
      aiApi.updateConfidenceThresholds(thresholds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: aiKeys.thresholds() });
    },
  });
}
