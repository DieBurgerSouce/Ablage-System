/**
 * API Client fuer Batch-OCR-Korrektur Feature
 */

import { apiClient } from '@/lib/api/client'
import type {
    BatchDocumentsResponse,
    BatchCorrectionPayload,
    BatchConfirmPayload,
} from '../types'

const BASE_URL = '/documents'

/**
 * Dokumente mit niedrigem OCR-Confidence abrufen.
 * Nutzt den bestehenden Documents-Endpunkt mit Filtern.
 */
export async function getLowConfidenceDocuments(params: {
    page?: number
    per_page?: number
    document_type?: string
    confidence_max?: number
    status?: string
    sort_by?: string
    sort_order?: string
}): Promise<BatchDocumentsResponse> {
    const searchParams = new URLSearchParams()
    if (params.page) searchParams.set('page', String(params.page))
    if (params.per_page) searchParams.set('per_page', String(params.per_page))
    if (params.document_type) searchParams.set('document_type', params.document_type)
    if (params.confidence_max !== undefined) searchParams.set('confidence_max', String(params.confidence_max))
    if (params.status) searchParams.set('ocr_status', params.status)
    searchParams.set('sort_by', params.sort_by || 'ocr_confidence')
    searchParams.set('sort_order', params.sort_order || 'asc')

    const query = searchParams.toString()
    const url = `${BASE_URL}${query ? `?${query}` : ''}`
    const response = await apiClient.get<BatchDocumentsResponse>(url)
    return response.data
}

/**
 * Korrekturen fuer ein einzelnes Dokument speichern.
 */
export async function saveCorrections(
    payload: BatchCorrectionPayload
): Promise<{ success: boolean; message: string }> {
    const response = await apiClient.patch<{ success: boolean; message: string }>(
        `${BASE_URL}/${payload.document_id}/ocr-corrections`,
        { corrections: payload.corrections }
    )
    return response.data
}

/**
 * Mehrere Dokumente als korrekt bestaetigen (Batch).
 */
export async function confirmDocuments(
    payload: BatchConfirmPayload
): Promise<{ success: boolean; confirmed_count: number }> {
    const response = await apiClient.post<{ success: boolean; confirmed_count: number }>(
        `${BASE_URL}/batch-confirm-ocr`,
        payload
    )
    return response.data
}

/**
 * Extrahierte Felder fuer ein Dokument abrufen.
 */
export async function getDocumentExtractedFields(
    documentId: string
): Promise<Record<string, { value: string | number | null; confidence: number; field_type: string }>> {
    const response = await apiClient.get<Record<string, { value: string | number | null; confidence: number; field_type: string }>>(
        `${BASE_URL}/${documentId}/extracted-fields`
    )
    return response.data
}

export const ocrBatchApi = {
    getLowConfidenceDocuments,
    saveCorrections,
    confirmDocuments,
    getDocumentExtractedFields,
}
