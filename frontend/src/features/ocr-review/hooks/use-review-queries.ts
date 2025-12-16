/**
 * TanStack Query Hooks für OCR Review Feature
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reviewApi } from '../api/review-api'
import type {
    QueueStats,
    QueueItem,
    TrainingSampleDetail,
    VerifyRequest,
    CorrectionCreate,
    LearnedWeights,
    LLMReviewResult,
} from '../types'

// Query Keys
export const reviewQueryKeys = {
    all: ['ocr-review'] as const,
    queueStats: () => [...reviewQueryKeys.all, 'queue-stats'] as const,
    nextSample: (type?: string) => [...reviewQueryKeys.all, 'next', type] as const,
    sample: (id: string) => [...reviewQueryKeys.all, 'sample', id] as const,
    learnedWeights: () => [...reviewQueryKeys.all, 'learned-weights'] as const,
    llmReview: (sampleId: string) => [...reviewQueryKeys.all, 'llm-review', sampleId] as const,
    coverage: () => [...reviewQueryKeys.all, 'coverage'] as const,
    samplesByType: (type: string) => [...reviewQueryKeys.all, 'by-type', type] as const,
}

/**
 * Queue Statistiken
 */
export function useQueueStats() {
    return useQuery<QueueStats>({
        queryKey: reviewQueryKeys.queueStats(),
        queryFn: reviewApi.getQueueStats,
        refetchInterval: 30000, // Alle 30 Sekunden
        staleTime: 10000,
    })
}

/**
 * Nächstes Sample aus Queue
 */
export function useNextSample(documentType?: string, enabled = true) {
    return useQuery<{ item: QueueItem | null }>({
        queryKey: reviewQueryKeys.nextSample(documentType),
        queryFn: () => reviewApi.getNextSample({
            document_type: documentType,
            include_spot_checks: true,
        }),
        enabled,
        staleTime: 0, // Immer frisch
        gcTime: 0, // Nicht cachen
    })
}

/**
 * Sample Details
 */
export function useSampleDetail(sampleId: string | undefined) {
    return useQuery<TrainingSampleDetail>({
        queryKey: reviewQueryKeys.sample(sampleId ?? ''),
        queryFn: () => reviewApi.getSampleDetail(sampleId!),
        enabled: !!sampleId,
        staleTime: 60000, // 1 Minute
    })
}

/**
 * LLM Review für Sample (automatisch laden wenn Sample geladen)
 */
export function useLLMReview(sampleId: string | undefined, autoFetch = true) {
    return useQuery<LLMReviewResult | null>({
        queryKey: reviewQueryKeys.llmReview(sampleId ?? ''),
        queryFn: async () => {
            if (!sampleId) return null
            // Erst prüfen ob bereits vorhanden
            const existing = await reviewApi.getLLMReviewResult(sampleId)
            if (existing) return existing
            // Falls nicht, neuen Review anfordern
            return reviewApi.getLLMReview(sampleId)
        },
        enabled: !!sampleId && autoFetch,
        staleTime: 300000, // 5 Minuten
        retry: 1,
    })
}

/**
 * Gelernte Gewichte
 */
export function useLearnedWeights(forceRefresh = false) {
    return useQuery<LearnedWeights>({
        queryKey: reviewQueryKeys.learnedWeights(),
        queryFn: () => reviewApi.getLearnedWeights(forceRefresh),
        staleTime: 60000, // 1 Minute
        refetchInterval: 120000, // Alle 2 Minuten
    })
}

/**
 * Coverage Status
 */
export function useCoverageStatus() {
    return useQuery({
        queryKey: reviewQueryKeys.coverage(),
        queryFn: reviewApi.getCoverageStatus,
        staleTime: 60000,
    })
}

/**
 * Samples nach Typ (für Listen-Ansicht)
 */
export function useSamplesByType(documentType: string, limit = 50, offset = 0) {
    return useQuery({
        queryKey: [...reviewQueryKeys.samplesByType(documentType), limit, offset],
        queryFn: () => reviewApi.getSamplesByType(documentType, { limit, offset }),
        enabled: !!documentType,
    })
}

/**
 * Sample verifizieren (Mutation)
 */
export function useVerifySample() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: ({ sampleId, data }: { sampleId: string; data: VerifyRequest }) =>
            reviewApi.verifySample(sampleId, data),
        onSuccess: () => {
            // Queue Stats und nächstes Sample invalidieren
            queryClient.invalidateQueries({ queryKey: reviewQueryKeys.queueStats() })
            queryClient.invalidateQueries({ queryKey: reviewQueryKeys.nextSample() })
            queryClient.invalidateQueries({ queryKey: reviewQueryKeys.coverage() })
        },
    })
}

/**
 * Korrektur einreichen (Mutation)
 */
export function useSubmitCorrection() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (data: CorrectionCreate) => reviewApi.submitCorrection(data),
        onSuccess: () => {
            // Learned Weights invalidieren
            queryClient.invalidateQueries({ queryKey: reviewQueryKeys.learnedWeights() })
        },
    })
}

/**
 * LLM Review anfordern (Mutation)
 */
export function useRequestLLMReview() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (sampleId: string) => reviewApi.getLLMReview(sampleId),
        onSuccess: (data, sampleId) => {
            // Cache aktualisieren
            queryClient.setQueryData(reviewQueryKeys.llmReview(sampleId), data)
        },
    })
}

/**
 * Prefetch nächstes Sample (für schnelleres Laden)
 */
export function usePrefetchNextSample() {
    const queryClient = useQueryClient()

    return (documentType?: string) => {
        queryClient.prefetchQuery({
            queryKey: reviewQueryKeys.nextSample(documentType),
            queryFn: () => reviewApi.getNextSample({
                document_type: documentType,
                include_spot_checks: true,
            }),
        })
    }
}
