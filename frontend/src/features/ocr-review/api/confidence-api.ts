/**
 * API Client für OCR-Confidence-Daten
 *
 * Kommuniziert mit /api/v1/ocr-confidence Endpoints.
 */

import { apiClient } from '@/lib/api/client'

// =============================================================================
// Types (matching backend response models)
// =============================================================================

export interface WordConfidence {
    text: string
    confidence: number // 0-1
    page: number
    x: number // normalized 0-1
    y: number // normalized 0-1
    width: number // normalized 0-1
    height: number // normalized 0-1
}

export interface PageConfidence {
    page_number: number
    overall_confidence: number
    words: WordConfidence[]
    backend: string
}

export interface DocumentConfidenceData {
    document_id: string
    total_pages: number
    overall_confidence: number
    pages: PageConfidence[]
    backend: string
}

export interface ConfidenceSummary {
    document_id: string
    overall_confidence: number
    total_pages: number
    backend: string
    page_averages: Record<number, number>
    has_word_level_data: boolean
}

// =============================================================================
// Confidence Level Helpers
// =============================================================================

export type ConfidenceLevel = 'critical' | 'low' | 'uncertain' | 'high'

export function getConfidenceLevel(confidence: number): ConfidenceLevel {
    if (confidence >= 0.95) return 'high'
    if (confidence >= 0.8) return 'uncertain'
    if (confidence >= 0.6) return 'low'
    return 'critical'
}

export function getConfidenceLevelLabel(level: ConfidenceLevel): string {
    switch (level) {
        case 'high':
            return 'Sicher'
        case 'uncertain':
            return 'Unsicher'
        case 'low':
            return 'Niedrig'
        case 'critical':
            return 'Kritisch'
    }
}

export function getConfidenceLevelColor(level: ConfidenceLevel): string {
    switch (level) {
        case 'high':
            return 'text-green-600 dark:text-green-400'
        case 'uncertain':
            return 'text-yellow-600 dark:text-yellow-400'
        case 'low':
            return 'text-orange-600 dark:text-orange-400'
        case 'critical':
            return 'text-red-600 dark:text-red-400'
    }
}

export function getConfidenceBgColor(level: ConfidenceLevel): string {
    switch (level) {
        case 'high':
            return 'bg-green-100 dark:bg-green-900/30'
        case 'uncertain':
            return 'bg-yellow-100 dark:bg-yellow-900/30'
        case 'low':
            return 'bg-orange-100 dark:bg-orange-900/30'
        case 'critical':
            return 'bg-red-100 dark:bg-red-900/30'
    }
}

export function getConfidenceOverlayColor(confidence: number): string {
    if (confidence >= 0.95) return 'rgba(34, 197, 94, 0.25)' // green
    if (confidence >= 0.8) return 'rgba(234, 179, 8, 0.3)' // yellow
    if (confidence >= 0.6) return 'rgba(249, 115, 22, 0.35)' // orange
    return 'rgba(239, 68, 68, 0.4)' // red
}

export function getConfidenceStrokeColor(confidence: number): string {
    if (confidence >= 0.95) return 'rgba(34, 197, 94, 0.7)'
    if (confidence >= 0.8) return 'rgba(234, 179, 8, 0.8)'
    if (confidence >= 0.6) return 'rgba(249, 115, 22, 0.8)'
    return 'rgba(239, 68, 68, 0.9)'
}

// =============================================================================
// API Functions
// =============================================================================

const BASE_URL = '/ocr-confidence'

/**
 * Hole detaillierte OCR-Confidence-Daten für ein Dokument.
 * Beinhaltet Wort-Level Daten mit Positionen.
 */
export async function getDocumentConfidence(
    documentId: string,
    pageNumber?: number
): Promise<DocumentConfidenceData> {
    const params = new URLSearchParams()
    if (pageNumber !== undefined) {
        params.set('page', String(pageNumber))
    }
    const query = params.toString()
    const url = `${BASE_URL}/${documentId}${query ? `?${query}` : ''}`
    const response = await apiClient.get<DocumentConfidenceData>(url)
    return response.data
}

/**
 * Hole schnelle Confidence-Zusammenfassung (ohne Wort-Daten).
 */
export async function getConfidenceSummary(
    documentId: string
): Promise<ConfidenceSummary> {
    const response = await apiClient.get<ConfidenceSummary>(
        `${BASE_URL}/${documentId}/summary`
    )
    return response.data
}

// Export als Objekt für einfachen Import
export const confidenceApi = {
    getDocumentConfidence,
    getConfidenceSummary,
}
