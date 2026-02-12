/**
 * Correction Workbench Hooks
 * TanStack Query Hooks für OCR-Korrektur-Workbench
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getLowConfidenceQueue,
  submitCorrection,
  submitBatchCorrections,
  getCorrectionStats,
  exportTrainingData,
  getExportList,
  deleteExport,
  getAvailableBackends,
} from './api';
import type {
  QueueFilters,
  CorrectionSubmission,
  TrainingExportConfig,
} from './types';

// Query Keys
export const correctionWorkbenchKeys = {
  all: ['correction-workbench'] as const,
  queue: (filters: QueueFilters, limit: number, offset: number) =>
    [...correctionWorkbenchKeys.all, 'queue', filters, limit, offset] as const,
  stats: () => [...correctionWorkbenchKeys.all, 'stats'] as const,
  exports: () => [...correctionWorkbenchKeys.all, 'exports'] as const,
  backends: () => [...correctionWorkbenchKeys.all, 'backends'] as const,
};

// Stale Times
const STALE_TIMES = {
  queue: 60 * 1000, // 1 Minute
  stats: 5 * 60 * 1000, // 5 Minuten
  exports: 10 * 60 * 1000, // 10 Minuten
  backends: 30 * 60 * 1000, // 30 Minuten
};

/**
 * Low-Confidence Queue abrufen
 */
export function useLowConfidenceQueue(
  filters: QueueFilters,
  limit = 50,
  offset = 0,
  enabled = true
) {
  return useQuery({
    queryKey: correctionWorkbenchKeys.queue(filters, limit, offset),
    queryFn: () => getLowConfidenceQueue(filters, limit, offset),
    staleTime: STALE_TIMES.queue,
    enabled,
  });
}

/**
 * Korrektur-Statistiken abrufen
 */
export function useCorrectionStats() {
  return useQuery({
    queryKey: correctionWorkbenchKeys.stats(),
    queryFn: getCorrectionStats,
    staleTime: STALE_TIMES.stats,
  });
}

/**
 * Verfügbare Backends abrufen
 */
export function useAvailableBackends() {
  return useQuery({
    queryKey: correctionWorkbenchKeys.backends(),
    queryFn: getAvailableBackends,
    staleTime: STALE_TIMES.backends,
  });
}

/**
 * Export-Liste abrufen
 */
export function useExportList() {
  return useQuery({
    queryKey: correctionWorkbenchKeys.exports(),
    queryFn: getExportList,
    staleTime: STALE_TIMES.exports,
  });
}

/**
 * Einzelne Korrektur einreichen
 */
export function useSubmitCorrection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (correction: CorrectionSubmission) => submitCorrection(correction),
    onSuccess: () => {
      // Queue und Stats invalidieren
      queryClient.invalidateQueries({
        queryKey: correctionWorkbenchKeys.all,
      });
    },
  });
}

/**
 * Batch-Korrekturen einreichen
 */
export function useSubmitBatchCorrections() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (corrections: CorrectionSubmission[]) =>
      submitBatchCorrections(corrections),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: correctionWorkbenchKeys.all,
      });
    },
  });
}

/**
 * Training-Daten exportieren
 */
export function useExportTrainingData() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (config: TrainingExportConfig) => exportTrainingData(config),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: correctionWorkbenchKeys.exports(),
      });
    },
  });
}

/**
 * Export löschen
 */
export function useDeleteExport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (exportId: string) => deleteExport(exportId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: correctionWorkbenchKeys.exports(),
      });
    },
  });
}
