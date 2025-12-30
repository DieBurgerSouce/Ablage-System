/**
 * Validation Query Hooks
 *
 * TanStack Query Hooks für das OCR-Training und Validierungs-System.
 * Enterprise-Level mit Caching, Optimistic Updates und Error Handling.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  listTrainingSamples,
  getTrainingSample,
  updateTrainingSample,
  verifyTrainingSample,
  listCorrections,
  createCorrection,
  listBatches,
  getBatch,
  createBatch,
  updateBatchItem,
  startBatch,
  completeBatch,
  getTrainingStats,
  getBackendComparison,
  runBenchmarks,
  type ListSamplesParams,
  type ListCorrectionsParams,
  type ListBatchesParams,
  type RunBenchmarkParams,
} from '../api/validation-api';
import type {
  TrainingSampleUpdate,
  CorrectionCreate,
  BatchCreate,
  BatchItemUpdate,
  TrainingSampleStatus,
} from '../types';

// ==================== Query Keys ====================

export const validationKeys = {
  all: ['validation'] as const,
  samples: () => [...validationKeys.all, 'samples'] as const,
  sampleList: (filters: ListSamplesParams) => [...validationKeys.samples(), 'list', filters] as const,
  sampleDetail: (id: string) => [...validationKeys.samples(), 'detail', id] as const,
  corrections: () => [...validationKeys.all, 'corrections'] as const,
  correctionList: (filters: ListCorrectionsParams) => [...validationKeys.corrections(), 'list', filters] as const,
  batches: () => [...validationKeys.all, 'batches'] as const,
  batchList: (filters: ListBatchesParams) => [...validationKeys.batches(), 'list', filters] as const,
  batchDetail: (id: string) => [...validationKeys.batches(), 'detail', id] as const,
  stats: () => [...validationKeys.all, 'stats'] as const,
  backendComparison: () => [...validationKeys.all, 'backendComparison'] as const,
};

// ==================== Sample Queries ====================

/**
 * Hook zum Abrufen der Training-Samples-Liste.
 */
export function useTrainingSamples(params: ListSamplesParams = {}) {
  return useQuery({
    queryKey: validationKeys.sampleList(params),
    queryFn: () => listTrainingSamples(params),
    staleTime: 30 * 1000, // 30 Sekunden
  });
}

/**
 * Hook zum Abrufen eines einzelnen Training-Samples.
 */
export function useTrainingSample(sampleId: string | undefined) {
  return useQuery({
    queryKey: validationKeys.sampleDetail(sampleId!),
    queryFn: () => getTrainingSample(sampleId!),
    enabled: !!sampleId,
    staleTime: 60 * 1000, // 1 Minute
  });
}

/**
 * Hook zum Aktualisieren eines Training-Samples.
 */
export function useUpdateTrainingSample() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ sampleId, data }: { sampleId: string; data: TrainingSampleUpdate }) =>
      updateTrainingSample(sampleId, data),
    onSuccess: (updatedSample) => {
      // Update einzelnes Sample im Cache
      queryClient.setQueryData(
        validationKeys.sampleDetail(updatedSample.id),
        updatedSample
      );
      // Invalidate Liste
      queryClient.invalidateQueries({ queryKey: validationKeys.samples() });
      toast.success('Sample erfolgreich aktualisiert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Hook zum Verifizieren eines Training-Samples (Admin).
 */
export function useVerifyTrainingSample() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      sampleId,
      approved,
      notes,
    }: {
      sampleId: string;
      approved: boolean;
      notes?: string;
    }) => verifyTrainingSample(sampleId, approved, notes),
    onSuccess: (updatedSample, variables) => {
      queryClient.setQueryData(
        validationKeys.sampleDetail(updatedSample.id),
        updatedSample
      );
      queryClient.invalidateQueries({ queryKey: validationKeys.samples() });
      queryClient.invalidateQueries({ queryKey: validationKeys.stats() });
      toast.success(
        variables.approved ? 'Sample verifiziert' : 'Sample abgelehnt'
      );
    },
    onError: (error: Error) => {
      toast.error(`Fehler bei der Verifizierung: ${error.message}`);
    },
  });
}

// ==================== Correction Queries ====================

/**
 * Hook zum Abrufen der Korrekturen-Liste.
 */
export function useCorrections(params: ListCorrectionsParams = {}) {
  return useQuery({
    queryKey: validationKeys.correctionList(params),
    queryFn: () => listCorrections(params),
    staleTime: 60 * 1000, // 1 Minute
  });
}

/**
 * Hook zum Erstellen einer Korrektur (Self-Learning).
 */
export function useCreateCorrection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CorrectionCreate) => createCorrection(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: validationKeys.corrections() });
      queryClient.invalidateQueries({ queryKey: validationKeys.stats() });
      toast.success('Korrektur gespeichert');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Speichern der Korrektur: ${error.message}`);
    },
  });
}

// ==================== Batch Queries ====================

/**
 * Hook zum Abrufen der Batch-Liste.
 */
export function useBatches(params: ListBatchesParams = {}) {
  return useQuery({
    queryKey: validationKeys.batchList(params),
    queryFn: () => listBatches(params),
    staleTime: 30 * 1000, // 30 Sekunden
  });
}

/**
 * Hook zum Abrufen eines einzelnen Batches mit Items.
 */
export function useBatch(batchId: string | undefined) {
  return useQuery({
    queryKey: validationKeys.batchDetail(batchId!),
    queryFn: () => getBatch(batchId!),
    enabled: !!batchId,
    staleTime: 30 * 1000,
  });
}

/**
 * Hook zum Erstellen eines Batches.
 */
export function useCreateBatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: BatchCreate) => createBatch(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: validationKeys.batches() });
      toast.success('Stichprobe erstellt');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Erstellen der Stichprobe: ${error.message}`);
    },
  });
}

/**
 * Hook zum Aktualisieren eines Batch-Items.
 */
export function useUpdateBatchItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      batchId,
      itemId,
      data,
    }: {
      batchId: string;
      itemId: string;
      data: BatchItemUpdate;
    }) => updateBatchItem(batchId, itemId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: validationKeys.batchDetail(variables.batchId),
      });
      queryClient.invalidateQueries({ queryKey: validationKeys.batches() });
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Aktualisieren: ${error.message}`);
    },
  });
}

/**
 * Hook zum Starten eines Batches.
 */
export function useStartBatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (batchId: string) => startBatch(batchId),
    onSuccess: (updatedBatch) => {
      queryClient.setQueryData(
        validationKeys.batchDetail(updatedBatch.id),
        updatedBatch
      );
      queryClient.invalidateQueries({ queryKey: validationKeys.batches() });
      toast.success('Stichprobe gestartet');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Starten: ${error.message}`);
    },
  });
}

/**
 * Hook zum Abschließen eines Batches.
 */
export function useCompleteBatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (batchId: string) => completeBatch(batchId),
    onSuccess: (updatedBatch) => {
      queryClient.setQueryData(
        validationKeys.batchDetail(updatedBatch.id),
        updatedBatch
      );
      queryClient.invalidateQueries({ queryKey: validationKeys.batches() });
      toast.success('Stichprobe abgeschlossen');
    },
    onError: (error: Error) => {
      toast.error(`Fehler beim Abschließen: ${error.message}`);
    },
  });
}

// Backward-compatibility (deprecated)
/** @deprecated Use useStartBatch instead */
export const useActivateBatch = useStartBatch;
/** @deprecated Use useCompleteBatch instead */
export const useCancelBatch = useCompleteBatch;

// ==================== Statistics Queries ====================

/**
 * Hook zum Abrufen der Übersichts-Statistiken.
 */
export function useTrainingStats() {
  return useQuery({
    queryKey: validationKeys.stats(),
    queryFn: getTrainingStats,
    staleTime: 60 * 1000, // 1 Minute
    refetchInterval: 5 * 60 * 1000, // Alle 5 Minuten aktualisieren
  });
}

/**
 * Hook zum Abrufen des Backend-Vergleichs.
 */
export function useBackendComparison() {
  return useQuery({
    queryKey: validationKeys.backendComparison(),
    queryFn: getBackendComparison,
    staleTime: 5 * 60 * 1000, // 5 Minuten
  });
}

// ==================== Benchmark Mutations ====================

/**
 * Hook zum Starten eines Benchmark-Laufs.
 */
export function useRunBenchmarks() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: RunBenchmarkParams) => runBenchmarks(params),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: validationKeys.samples() });
      queryClient.invalidateQueries({ queryKey: validationKeys.backendComparison() });
      toast.success(
        `Benchmark abgeschlossen: ${result.samples_processed} Samples verarbeitet`
      );
    },
    onError: (error: Error) => {
      toast.error(`Benchmark-Fehler: ${error.message}`);
    },
  });
}

// ==================== Convenience Hooks ====================

/**
 * Hook für ausstehende Samples (Validierungs-Queue).
 */
export function usePendingSamples(limit: number = 50, offset: number = 0) {
  return useTrainingSamples({
    status: 'pending' as TrainingSampleStatus,
    limit,
    offset,
  });
}

/**
 * Hook für Samples, die verifiziert werden müssen (Admin).
 */
export function useAnnotatedSamples(limit: number = 50, offset: number = 0) {
  return useTrainingSamples({
    status: 'annotated' as TrainingSampleStatus,
    limit,
    offset,
  });
}

/**
 * Hook für aktive Batches.
 */
export function useActiveBatches() {
  return useBatches({ status: 'active' });
}
