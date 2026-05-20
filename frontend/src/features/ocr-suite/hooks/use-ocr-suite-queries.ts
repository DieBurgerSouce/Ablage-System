import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getOcrRegions,
  submitOcrFeedback,
  getSelfLearningStats,
  getDocumentVersions,
} from '../api';
import type { OcrFeedbackRequest } from '../types';

// ============================================================================
// Query Keys
// ============================================================================

export const ocrSuiteKeys = {
  all: ['ocr-suite'] as const,
  regions: (documentId: string) => ['ocr-suite', 'regions', documentId] as const,
  stats: () => ['ocr-suite', 'stats'] as const,
  versions: (documentId: string) => ['ocr-suite', 'versions', documentId] as const,
};

// ============================================================================
// OCR Regions Query
// ============================================================================

export function useOcrRegions(documentId: string | undefined) {
  return useQuery({
    queryKey: ocrSuiteKeys.regions(documentId || ''),
    queryFn: () => getOcrRegions(documentId!),
    enabled: !!documentId,
  });
}

// ============================================================================
// OCR Feedback Mutation
// ============================================================================

export function useSubmitOcrFeedback() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      documentId,
      feedback,
    }: {
      documentId: string;
      feedback: OcrFeedbackRequest;
    }) => submitOcrFeedback(documentId, feedback),
    onSuccess: (_, { documentId }) => {
      // Invalidate regions to refresh confidence scores
      queryClient.invalidateQueries({
        queryKey: ocrSuiteKeys.regions(documentId),
      });
      // Invalidate stats to update correction count
      queryClient.invalidateQueries({
        queryKey: ocrSuiteKeys.stats(),
      });
    },
  });
}

// ============================================================================
// Self-Learning Stats Query
// ============================================================================

export function useSelfLearningStats() {
  return useQuery({
    queryKey: ocrSuiteKeys.stats(),
    queryFn: getSelfLearningStats,
    refetchInterval: 30000, // Refresh every 30 seconds
  });
}

// ============================================================================
// Document Versions Query
// ============================================================================

export function useDocumentVersions(documentId: string | undefined) {
  return useQuery({
    queryKey: ocrSuiteKeys.versions(documentId || ''),
    queryFn: () => getDocumentVersions(documentId!),
    enabled: !!documentId,
  });
}
