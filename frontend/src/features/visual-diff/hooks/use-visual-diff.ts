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
