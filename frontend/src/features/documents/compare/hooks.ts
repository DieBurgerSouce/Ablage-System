/**
 * Document Comparison Hooks
 *
 * TanStack Query Hooks fuer Dokumentenvergleiche.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { ComparisonType } from './types';
import {
  compareDocuments,
  getDiffReport,
  findSimilarDocuments,
  findPotentialDuplicates,
} from './api';

// Query Key Factory
export const compareKeys = {
  all: ['compare'] as const,
  comparison: (docId1: string, docId2: string, type?: ComparisonType) =>
    [...compareKeys.all, 'comparison', docId1, docId2, type] as const,
  diffReport: (docId1: string, docId2: string, type?: ComparisonType) =>
    [...compareKeys.all, 'diff-report', docId1, docId2, type] as const,
  similar: (docId: string, threshold?: number) =>
    [...compareKeys.all, 'similar', docId, threshold] as const,
  duplicates: (threshold?: number, daysBack?: number) =>
    [...compareKeys.all, 'duplicates', threshold, daysBack] as const,
};

/**
 * Hook fuer den Vergleich zweier Dokumente.
 */
export function useCompareDocuments() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: compareDocuments,
    onSuccess: (data) => {
      queryClient.setQueryData(
        compareKeys.comparison(data.documentId1, data.documentId2, data.comparisonType),
        data
      );
    },
  });
}

/**
 * Hook fuer einen Diff-Report.
 */
export function useDiffReport(
  docId1: string,
  docId2: string,
  comparisonType: ComparisonType = 'hybrid',
  enabled: boolean = true
) {
  return useQuery({
    queryKey: compareKeys.diffReport(docId1, docId2, comparisonType),
    queryFn: () => getDiffReport(docId1, docId2, comparisonType),
    enabled: enabled && !!docId1 && !!docId2,
    staleTime: 5 * 60 * 1000, // 5 Minuten
  });
}

/**
 * Hook fuer aehnliche Dokumente.
 */
export function useSimilarDocuments(
  docId: string,
  threshold: number = 0.8,
  limit: number = 10,
  includeSameEntity: boolean = true,
  enabled: boolean = true
) {
  return useQuery({
    queryKey: compareKeys.similar(docId, threshold),
    queryFn: () => findSimilarDocuments(docId, threshold, limit, includeSameEntity),
    enabled: enabled && !!docId,
    staleTime: 10 * 60 * 1000, // 10 Minuten
  });
}

/**
 * Hook fuer potenzielle Duplikate.
 */
export function usePotentialDuplicates(
  threshold: number = 0.95,
  daysBack: number = 30,
  limit: number = 50,
  enabled: boolean = true
) {
  return useQuery({
    queryKey: compareKeys.duplicates(threshold, daysBack),
    queryFn: () => findPotentialDuplicates(threshold, daysBack, limit),
    enabled,
    staleTime: 15 * 60 * 1000, // 15 Minuten
  });
}
