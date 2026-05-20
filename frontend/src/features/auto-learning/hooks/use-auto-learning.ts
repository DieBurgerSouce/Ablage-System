/**
 * Auto-Learning TanStack Query Hooks
 *
 * Hooks fuer KI-Entscheidungen, Review-Batch, Statistiken
 * und den Pending-Review-Count (Badge im Header).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { autoLearningApi } from '../api/auto-learning-api'
import type { ReviewPayload } from '../types'

// ==================== Query Keys ====================

export const autoLearningQueryKeys = {
    all: ['auto-learning'] as const,
    decisions: (params?: Record<string, unknown>) =>
        [...autoLearningQueryKeys.all, 'decisions', params] as const,
    reviewBatch: () =>
        [...autoLearningQueryKeys.all, 'review-batch'] as const,
    stats: (days?: number) =>
        [...autoLearningQueryKeys.all, 'stats', days] as const,
    learningProgress: (days?: number) =>
        [...autoLearningQueryKeys.all, 'learning-progress', days] as const,
    pendingCount: () =>
        [...autoLearningQueryKeys.all, 'pending-count'] as const,
}

// ==================== Hooks ====================

/**
 * Letzte automatisch angewandte KI-Aktionen abrufen.
 * Filtert client-seitig auf auto_applied, da das Backend
 * diesen Filter im GET /ai/decisions nicht direkt unterstuetzt.
 */
export function useRecentAutoActions(limit = 50) {
    return useQuery({
        queryKey: autoLearningQueryKeys.decisions({ autoApplied: true, limit }),
        queryFn: async () => {
            const decisions = await autoLearningApi.getDecisions({ limit: limit * 2 })
            return decisions.filter((d) => d.autoApplied).slice(0, limit)
        },
        staleTime: 30_000,
    })
}

/**
 * Entscheidungen die eine manuelle Pruefung erfordern.
 */
export function useReviewBatch() {
    return useQuery({
        queryKey: autoLearningQueryKeys.reviewBatch(),
        queryFn: () =>
            autoLearningApi.getDecisions({
                requiresReview: true,
                limit: 100,
            }),
        staleTime: 30_000,
    })
}

/**
 * Genauigkeitsstatistiken fuer den angegebenen Zeitraum.
 */
export function useLearningStats(days = 30) {
    return useQuery({
        queryKey: autoLearningQueryKeys.stats(days),
        queryFn: () => autoLearningApi.getAccuracyStats(days),
        staleTime: 60_000,
    })
}

/**
 * Anzahl offener Pruefungen (fuer Badge im Header).
 * Wird haeufig aktualisiert da Badge sichtbar bleibt.
 */
export function usePendingReviewCount() {
    return useQuery({
        queryKey: autoLearningQueryKeys.pendingCount(),
        queryFn: () => autoLearningApi.getPendingReviewCount(),
        staleTime: 15_000,
        refetchInterval: 60_000,
    })
}

/**
 * Mutation zum Pruefen einer KI-Entscheidung.
 * Invalidiert alle Auto-Learning-Queries bei Erfolg.
 */
export function useReviewDecision() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: ({
            decisionId,
            payload,
        }: {
            decisionId: string
            payload: ReviewPayload
        }) => autoLearningApi.reviewDecision(decisionId, payload),
        onSuccess: () => {
            queryClient.invalidateQueries({
                queryKey: autoLearningQueryKeys.all,
            })
        },
    })
}
