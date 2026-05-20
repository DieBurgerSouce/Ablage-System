/**
 * Auto-Learning API Client
 *
 * Kommuniziert mit den /api/v1/ai/* Endpoints.
 * Transformiert snake_case (Backend) -> camelCase (Frontend).
 */

import { apiClient } from '@/lib/api/client'
import type { AIDecision, AccuracyStats, ReviewPayload } from '../types'

// ==================== Backend Types (snake_case) ====================

interface AIDecisionBackend {
    id: string
    decision_type: string
    document_id: string | null
    decision_value: Record<string, unknown>
    confidence: number
    calibrated_confidence: number | null
    confidence_level: string
    auto_applied: boolean
    requires_review: boolean
    is_final: boolean
    explanation: Record<string, unknown> | null
    reviewed_by_id: string | null
    reviewed_at: string | null
    review_action: string | null
    created_at: string
}

interface AccuracyStatsBackend {
    decision_type: string
    total_decisions: number
    auto_applied: number
    reviewed: number
    approved: number
    corrected: number
    rejected: number
    accuracy_rate: number
    correction_rate: number
    avg_confidence: number
}

// ==================== Transformers ====================

function transformDecision(d: AIDecisionBackend): AIDecision {
    return {
        id: d.id,
        decisionType: d.decision_type,
        documentId: d.document_id,
        decisionValue: d.decision_value,
        confidence: d.confidence,
        calibratedConfidence: d.calibrated_confidence,
        confidenceLevel: d.confidence_level,
        autoApplied: d.auto_applied,
        requiresReview: d.requires_review,
        isFinal: d.is_final,
        explanation: d.explanation,
        reviewedById: d.reviewed_by_id,
        reviewedAt: d.reviewed_at,
        reviewAction: d.review_action,
        createdAt: d.created_at,
    }
}

function transformStats(s: AccuracyStatsBackend): AccuracyStats {
    return {
        decisionType: s.decision_type,
        totalDecisions: s.total_decisions,
        autoApplied: s.auto_applied,
        reviewed: s.reviewed,
        approved: s.approved,
        corrected: s.corrected,
        rejected: s.rejected,
        accuracyRate: s.accuracy_rate,
        correctionRate: s.correction_rate,
        avgConfidence: s.avg_confidence,
    }
}

// ==================== API Client ====================

export const autoLearningApi = {
    /**
     * KI-Entscheidungen abrufen mit optionalen Filtern.
     */
    async getDecisions(params: {
        decisionType?: string
        requiresReview?: boolean
        autoApplied?: boolean
        limit?: number
        offset?: number
    }): Promise<AIDecision[]> {
        const queryParams: Record<string, unknown> = {}

        if (params.decisionType) queryParams.decision_type = params.decisionType
        if (params.requiresReview !== undefined) queryParams.requires_review = params.requiresReview
        if (params.autoApplied !== undefined) queryParams.auto_applied = params.autoApplied
        if (params.limit !== undefined) queryParams.limit = params.limit
        if (params.offset !== undefined) queryParams.offset = params.offset

        const response = await apiClient.get<AIDecisionBackend[]>('/ai/decisions', {
            params: queryParams,
        })

        return response.data.map(transformDecision)
    },

    /**
     * KI-Entscheidung pruefen (akzeptieren / ablehnen / aendern).
     */
    async reviewDecision(
        decisionId: string,
        payload: ReviewPayload
    ): Promise<{ success: boolean; message: string }> {
        const body: Record<string, unknown> = {
            action: payload.action,
        }

        if (payload.modifiedValue) body.modified_value = payload.modifiedValue
        if (payload.comment) body.comment = payload.comment

        const response = await apiClient.post<{ success: boolean; message: string }>(
            `/ai/decisions/${decisionId}/review`,
            body
        )

        return response.data
    },

    /**
     * Genauigkeitsstatistiken abrufen.
     */
    async getAccuracyStats(days = 30): Promise<AccuracyStats[]> {
        const response = await apiClient.get<AccuracyStatsBackend[]>('/ai/stats/accuracy', {
            params: { days },
        })

        return response.data.map(transformStats)
    },

    /**
     * Lernfortschritt abrufen.
     */
    async getLearningProgress(days = 30): Promise<Record<string, unknown>> {
        const response = await apiClient.get<Record<string, unknown>>('/ai/stats/learning', {
            params: { days },
        })

        return response.data
    },

    /**
     * Anzahl offener Pruefungen pro Entscheidungstyp.
     */
    async getPendingReviewCount(): Promise<Record<string, number>> {
        const response = await apiClient.get<Record<string, number>>('/ai/pending-review-count')

        return response.data
    },
}
