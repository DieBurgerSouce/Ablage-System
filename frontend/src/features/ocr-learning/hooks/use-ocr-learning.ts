/**
 * OCR Self-Learning React Query Hooks
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { submitCorrectionFeedback, getCalibratedConfidence, getConfidenceStats, startABTest, getABTestResult, endABTest, getLearningStats, setLearningMode, getCurrentModelVersion, type CorrectionFeedbackRequest, type CalibratedConfidenceRequest, type ABTestStartRequest } from '../api/ocr-learning-api';

// ==================== Query Keys ====================

export const ocrLearningKeys = {
  all: ['ocr-learning'] as const,
  stats: () => [...ocrLearningKeys.all, 'stats'] as const,
  confidenceStats: (backend?: string) =>
    [...ocrLearningKeys.all, 'confidence-stats', backend] as const,
  abTest: (testId: string) => [...ocrLearningKeys.all, 'ab-test', testId] as const,
  modelVersion: (testId?: string) =>
    [...ocrLearningKeys.all, 'model-version', testId] as const,
};

// ==================== Hooks ====================

/**
 * Hook für Learning-Statistiken
 */
export function useLearningStats() {
  return useQuery({
    queryKey: ocrLearningKeys.stats(),
    queryFn: getLearningStats,
    staleTime: 30 * 1000, // 30 Sekunden
    refetchInterval: 60 * 1000, // Jede Minute
  });
}

/**
 * Hook für Confidence-Statistiken
 */
export function useConfidenceStats(backend?: string) {
  return useQuery({
    queryKey: ocrLearningKeys.confidenceStats(backend),
    queryFn: () => getConfidenceStats(backend),
    staleTime: 60 * 1000,
  });
}

/**
 * Hook für A/B Test Ergebnis
 */
export function useABTestResult(testId: string | undefined) {
  return useQuery({
    queryKey: ocrLearningKeys.abTest(testId || ''),
    queryFn: () => getABTestResult(testId!),
    enabled: !!testId,
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
}

/**
 * Hook für aktuelle Modell-Version
 */
export function useCurrentModelVersion(testId?: string) {
  return useQuery({
    queryKey: ocrLearningKeys.modelVersion(testId),
    queryFn: () => getCurrentModelVersion(testId),
    staleTime: 5 * 1000,
  });
}

/**
 * Mutation Hook für Korrektur-Feedback
 */
export function useSubmitCorrectionFeedback() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (feedback: CorrectionFeedbackRequest) =>
      submitCorrectionFeedback(feedback),
    onSuccess: () => {
      // Invalidate stats
      queryClient.invalidateQueries({ queryKey: ocrLearningKeys.stats() });
      queryClient.invalidateQueries({
        queryKey: ocrLearningKeys.confidenceStats(),
      });
    },
  });
}

/**
 * Mutation Hook für Confidence-Kalibrierung
 */
export function useCalibrateConfidence() {
  return useMutation({
    mutationFn: (request: CalibratedConfidenceRequest) =>
      getCalibratedConfidence(request),
  });
}

/**
 * Mutation Hook zum Starten eines A/B Tests
 */
export function useStartABTest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: ABTestStartRequest) => startABTest(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ocrLearningKeys.stats() });
    },
  });
}

/**
 * Mutation Hook zum Beenden eines A/B Tests
 */
export function useEndABTest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      testId,
      action,
    }: {
      testId: string;
      action: 'promote' | 'rollback';
    }) => endABTest(testId, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ocrLearningKeys.stats() });
    },
  });
}

/**
 * Mutation Hook zum Setzen des Learning-Modus
 */
export function useSetLearningMode() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (mode: 'aggressive' | 'cautious' | 'batch') =>
      setLearningMode(mode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ocrLearningKeys.stats() });
    },
  });
}
