/**
 * API Client für OCR Review Feature
 */

import { apiClient } from '@/lib/api/client'
import type {
    QueueStats,
    QueueItem,
    TrainingSampleDetail,
    VerifyRequest,
    CorrectionCreate,
    LearnedWeights,
    LLMReviewResult,
} from '../types'

const BASE_URL = '/training'

/**
 * Queue Statistiken abrufen
 */
export async function getQueueStats(): Promise<QueueStats> {
    const response = await apiClient.get<QueueStats>(`${BASE_URL}/verification-queue/stats`)
    return response.data
}

/**
 * Nächstes Sample aus der Queue holen
 */
export async function getNextSample(params?: {
    document_type?: string
    include_spot_checks?: boolean
}): Promise<{ item: QueueItem | null }> {
    const searchParams = new URLSearchParams()
    if (params?.document_type) {
        searchParams.set('document_type', params.document_type)
    }
    if (params?.include_spot_checks !== undefined) {
        searchParams.set('include_spot_checks', String(params.include_spot_checks))
    }
    const query = searchParams.toString()
    const url = `${BASE_URL}/verification-queue/next${query ? `?${query}` : ''}`
    const response = await apiClient.get<{ item: QueueItem | null }>(url)
    return response.data
}

/**
 * Sample Details abrufen
 */
export async function getSampleDetail(sampleId: string): Promise<TrainingSampleDetail> {
    const response = await apiClient.get<TrainingSampleDetail>(`${BASE_URL}/samples/${sampleId}`)
    return response.data
}

/**
 * Sample verifizieren (approve/reject/correct)
 */
export async function verifySample(
    sampleId: string,
    data: VerifyRequest
): Promise<{ success: boolean; message: string }> {
    const response = await apiClient.post<{ success: boolean; message: string }>(
        `${BASE_URL}/verification-queue/${sampleId}/verify`,
        data
    )
    return response.data
}

/**
 * Korrektur für Self-Learning einreichen
 */
export async function submitCorrection(
    data: CorrectionCreate
): Promise<{ id: string; message: string }> {
    const response = await apiClient.post<{ id: string; message: string }>(
        `${BASE_URL}/corrections`,
        data
    )
    return response.data
}

/**
 * Gelernte Gewichte abrufen
 */
export async function getLearnedWeights(forceRefresh = false): Promise<LearnedWeights> {
    const url = forceRefresh
        ? `${BASE_URL}/stats/learned-weights?force_refresh=true`
        : `${BASE_URL}/stats/learned-weights`
    const response = await apiClient.get<LearnedWeights>(url)
    return response.data
}

/**
 * LLM Review für Sample anfordern
 */
export async function getLLMReview(sampleId: string): Promise<LLMReviewResult> {
    const response = await apiClient.post<LLMReviewResult>(
        `${BASE_URL}/samples/${sampleId}/llm-review`,
        {}
    )
    return response.data
}

/**
 * LLM Review Ergebnis abrufen (falls bereits vorhanden)
 */
export async function getLLMReviewResult(sampleId: string): Promise<LLMReviewResult | null> {
    try {
        const response = await apiClient.get<LLMReviewResult>(
            `${BASE_URL}/samples/${sampleId}/llm-review/result`
        )
        return response.data
    } catch {
        // Falls noch kein Review vorhanden
        return null
    }
}

/**
 * Coverage Status abrufen
 */
export async function getCoverageStatus(): Promise<{
    coverage_by_type: Record<string, { current: number; target: number; count: number }>
    gaps: Array<{ document_type: string; gap_percent: number }>
}> {
    const response = await apiClient.get<{
        coverage_by_type: Record<string, { current: number; target: number; count: number }>
        gaps: Array<{ document_type: string; gap_percent: number }>
    }>(`${BASE_URL}/coverage/status`)
    return response.data
}

/**
 * Alle Samples nach Typ abrufen (für Listen-Ansicht)
 */
export async function getSamplesByType(
    documentType: string,
    params?: { limit?: number; offset?: number }
): Promise<{ items: QueueItem[]; total: number }> {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.set('limit', String(params.limit))
    if (params?.offset) searchParams.set('offset', String(params.offset))
    const query = searchParams.toString()
    const url = `${BASE_URL}/verification-queue/by-type/${documentType}${query ? `?${query}` : ''}`
    const response = await apiClient.get<{ items: QueueItem[]; total: number }>(url)
    return response.data
}

/**
 * Generiert die URL für die Dokument-Vorschau eines Samples
 */
export function getSamplePreviewUrl(sampleId: string, page: number = 0): string {
    // Nutze den apiClient baseURL für konsistente URL-Generierung
    const baseUrl = apiClient.defaults.baseURL || ''
    return `${baseUrl}/training/samples/${sampleId}/preview?page=${page}`
}

// Export als Objekt für einfachen Import
export const reviewApi = {
    getQueueStats,
    getNextSample,
    getSampleDetail,
    verifySample,
    submitCorrection,
    getLearnedWeights,
    getLLMReview,
    getLLMReviewResult,
    getCoverageStatus,
    getSamplesByType,
    getSamplePreviewUrl,
}
