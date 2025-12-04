/**
 * Zentrale Query Hooks für OCR-Training
 * Konsistente Query-Keys und wiederverwendbare Hooks
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { trainingService } from '@/lib/api/services/training';

// ==================== Query Keys ====================

export const trainingQueryKeys = {
    all: ['training'] as const,
    comparison: () => [...trainingQueryKeys.all, 'comparison'] as const,
    learnedWeights: (forceRefresh: boolean) => [...trainingQueryKeys.all, 'learned-weights', forceRefresh] as const,
    backends: () => [...trainingQueryKeys.all, 'backends'] as const,
    overview: () => [...trainingQueryKeys.all, 'overview'] as const,
    backendStats: (days: number) => [...trainingQueryKeys.all, 'backend-stats', days] as const,
    trends: (backend?: string, days?: number) => [...trainingQueryKeys.all, 'trends', backend, days] as const,
    samples: (params?: Record<string, unknown>) => [...trainingQueryKeys.all, 'samples', params] as const,
    sample: (id: string) => [...trainingQueryKeys.all, 'sample', id] as const,
    sampleBenchmarks: (id: string) => [...trainingQueryKeys.all, 'sample-benchmarks', id] as const,
    batches: (params?: Record<string, unknown>) => [...trainingQueryKeys.all, 'batches', params] as const,
    batch: (id: string) => [...trainingQueryKeys.all, 'batch', id] as const,
    corrections: (params?: Record<string, unknown>) => [...trainingQueryKeys.all, 'corrections', params] as const,
};

// ==================== Query Hooks ====================

/**
 * Backend-Vergleich abrufen
 */
export function useBackendComparison() {
    return useQuery({
        queryKey: trainingQueryKeys.comparison(),
        queryFn: () => trainingService.getBackendComparison(),
    });
}

/**
 * Gelernte Gewichtungen abrufen
 */
export function useLearnedWeights(forceRefresh = false) {
    return useQuery({
        queryKey: trainingQueryKeys.learnedWeights(forceRefresh),
        queryFn: () => trainingService.getLearnedWeights(forceRefresh),
    });
}

/**
 * Verfügbare Backends abrufen
 */
export function useAvailableBackends() {
    return useQuery({
        queryKey: trainingQueryKeys.backends(),
        queryFn: () => trainingService.getAvailableBackends(),
    });
}

/**
 * Übersichts-Statistiken abrufen
 */
export function useOverviewStats() {
    return useQuery({
        queryKey: trainingQueryKeys.overview(),
        queryFn: () => trainingService.getOverviewStats(),
    });
}

/**
 * Backend-Statistiken für einen Zeitraum abrufen
 */
export function useBackendStats(days = 30) {
    return useQuery({
        queryKey: trainingQueryKeys.backendStats(days),
        queryFn: () => trainingService.getBackendStats(days),
    });
}

/**
 * Trend-Daten abrufen
 */
export function useTrendData(params?: { backend?: string; days?: number }) {
    return useQuery({
        queryKey: trainingQueryKeys.trends(params?.backend, params?.days),
        queryFn: () => trainingService.getTrendData(params),
    });
}

/**
 * Samples auflisten
 */
export function useSamples(params?: {
    status?: string;
    language?: string;
    document_type?: string;
    has_ground_truth?: boolean;
    verified_only?: boolean;
    limit?: number;
    offset?: number;
}) {
    return useQuery({
        queryKey: trainingQueryKeys.samples(params),
        queryFn: () => trainingService.listSamples(params),
    });
}

/**
 * Einzelnes Sample abrufen
 */
export function useSample(id: string, enabled = true) {
    return useQuery({
        queryKey: trainingQueryKeys.sample(id),
        queryFn: () => trainingService.getSample(id),
        enabled,
    });
}

/**
 * Sample-Benchmarks abrufen
 */
export function useSampleBenchmarks(sampleId: string, enabled = true) {
    return useQuery({
        queryKey: trainingQueryKeys.sampleBenchmarks(sampleId),
        queryFn: () => trainingService.getSampleBenchmarks(sampleId),
        enabled,
    });
}

/**
 * Batches auflisten
 */
export function useBatches(params?: {
    status?: string;
    limit?: number;
    offset?: number;
}) {
    return useQuery({
        queryKey: trainingQueryKeys.batches(params),
        queryFn: () => trainingService.listBatches(params),
    });
}

/**
 * Einzelnen Batch abrufen
 */
export function useBatch(id: string, enabled = true) {
    return useQuery({
        queryKey: trainingQueryKeys.batch(id),
        queryFn: () => trainingService.getBatch(id),
        enabled,
    });
}

// ==================== Mutation Hooks ====================

/**
 * Benchmark starten
 */
export function useRunBenchmark() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: {
            sample_ids: string[];
            backends?: string[];
            force_reprocess?: boolean;
        }) => trainingService.runBenchmark(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.comparison() });
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.samples() });
        },
    });
}

/**
 * Sample aktualisieren
 */
export function useUpdateSample() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, data }: { id: string; data: Parameters<typeof trainingService.updateSample>[1] }) =>
            trainingService.updateSample(id, data),
        onSuccess: (_, { id }) => {
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.sample(id) });
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.samples() });
        },
    });
}

/**
 * Sample verifizieren
 */
export function useVerifySample() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, approved, notes }: { id: string; approved: boolean; notes?: string }) =>
            trainingService.verifySample(id, approved, notes),
        onSuccess: (_, { id }) => {
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.sample(id) });
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.samples() });
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.overview() });
        },
    });
}

/**
 * Sample löschen
 */
export function useDeleteSample() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (id: string) => trainingService.deleteSample(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.samples() });
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.overview() });
        },
    });
}

/**
 * Batch erstellen
 */
export function useCreateBatch() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: Parameters<typeof trainingService.createBatch>[0]) =>
            trainingService.createBatch(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.batches() });
        },
    });
}

/**
 * Batch starten
 */
export function useStartBatch() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (id: string) => trainingService.startBatch(id),
        onSuccess: (_, id) => {
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.batch(id) });
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.batches() });
        },
    });
}

/**
 * Batch abschließen
 */
export function useCompleteBatch() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (id: string) => trainingService.completeBatch(id),
        onSuccess: (_, id) => {
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.batch(id) });
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.batches() });
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.overview() });
        },
    });
}

/**
 * Batch-Item aktualisieren
 */
export function useUpdateBatchItem() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ batchId, itemId, data }: {
            batchId: string;
            itemId: string;
            data: Parameters<typeof trainingService.updateBatchItem>[2];
        }) => trainingService.updateBatchItem(batchId, itemId, data),
        onSuccess: (_, { batchId }) => {
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.batch(batchId) });
        },
    });
}

/**
 * Korrektur einreichen
 */
export function useCreateCorrection() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (data: Parameters<typeof trainingService.createCorrection>[0]) =>
            trainingService.createCorrection(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.overview() });
            queryClient.invalidateQueries({ queryKey: trainingQueryKeys.learnedWeights(false) });
        },
    });
}
