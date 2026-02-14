/**
 * Auto-Learning / KI-Entscheidungen - Type Definitions
 *
 * Frontend-Typen (camelCase) fuer die AI Decision API.
 * Backend liefert snake_case - Transformation erfolgt in auto-learning-api.ts
 */

export interface AIDecision {
    id: string
    decisionType: string
    documentId: string | null
    decisionValue: Record<string, unknown>
    confidence: number
    calibratedConfidence: number | null
    confidenceLevel: string
    autoApplied: boolean
    requiresReview: boolean
    isFinal: boolean
    explanation: Record<string, unknown> | null
    reviewedById: string | null
    reviewedAt: string | null
    reviewAction: string | null
    createdAt: string
}

export interface AccuracyStats {
    decisionType: string
    totalDecisions: number
    autoApplied: number
    reviewed: number
    approved: number
    corrected: number
    rejected: number
    accuracyRate: number
    correctionRate: number
    avgConfidence: number
}

export type ReviewActionType = 'approved' | 'rejected' | 'modified'

export interface ReviewPayload {
    action: ReviewActionType
    modifiedValue?: Record<string, unknown>
    comment?: string
}
