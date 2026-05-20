/**
 * Visual Diff Hooks - TanStack Query Integration
 *
 * React Hooks für den visuellen Dokumentenvergleich
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  compareTexts,
  compareTextsSummary,
  computeTextHash,
  visualDiffKeys,
  type DiffRequest,
} from '../api/visual-diff-api';
import { toast } from 'sonner';

/**
 * Mutation für vollständigen Textvergleich
 */
export function useCompareDiff() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: DiffRequest) => compareTexts(request),
    onSuccess: () => {
      // Invalidate related queries if needed
      queryClient.invalidateQueries({ queryKey: visualDiffKeys.all });
    },
    onError: (error: Error) => {
      toast.error('Vergleich fehlgeschlagen', {
        description: error.message || 'Der Textvergleich konnte nicht durchgeführt werden.',
      });
    },
  });
}

/**
 * Mutation für Änderungszusammenfassung
 */
export function useChangeSummary() {
  return useMutation({
    mutationFn: (request: DiffRequest) => compareTextsSummary(request),
    onError: (error: Error) => {
      toast.error('Zusammenfassung fehlgeschlagen', {
        description: error.message || 'Die Zusammenfassung konnte nicht erstellt werden.',
      });
    },
  });
}

/**
 * Mutation für Text-Hash-Berechnung
 */
export function useComputeHash() {
  return useMutation({
    mutationFn: (text: string) => computeTextHash(text),
    onError: (error: Error) => {
      toast.error('Hash-Berechnung fehlgeschlagen', {
        description: error.message || 'Der Hash konnte nicht berechnet werden.',
      });
    },
  });
}

/**
 * Mutation fuer Dokumenten-Vergleich (zwei Dokument-IDs)
 */
export function useCompareDocuments() {
  return useMutation({
    mutationFn: async ({
      documentId1,
      documentId2,
    }: {
      documentId1: string;
      documentId2: string;
    }) => {
      const { compareDocuments } = await import(
        '@/features/documents/compare/api'
      );
      return compareDocuments({
        documentId1,
        documentId2,
        comparisonType: 'hybrid',
      });
    },
    onError: (error: Error) => {
      toast.error('Dokumenten-Vergleich fehlgeschlagen', {
        description:
          error.message ||
          'Der Vergleich konnte nicht durchgefuehrt werden.',
      });
    },
  });
}

/**
 * Mutation fuer pixelweisen Bild-Vergleich zweier Dokumente
 */
export function useImageDiff() {
  return useMutation({
    mutationFn: async (params: {
      documentAId: string;
      documentBId: string;
      page?: number;
      threshold?: number;
    }) => {
      const { compareDocumentImages } = await import('../api/visual-diff-api');
      return compareDocumentImages({
        document_a_id: params.documentAId,
        document_b_id: params.documentBId,
        page: params.page,
        threshold: params.threshold,
      });
    },
    onError: (error: Error) => {
      toast.error('Bild-Vergleich fehlgeschlagen', {
        description:
          error.message ||
          'Der Bild-Vergleich konnte nicht durchgefuehrt werden.',
      });
    },
  });
}
