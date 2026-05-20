/**
 * TanStack Query Hooks für OCR-Confidence-Daten
 */

import { useQuery } from '@tanstack/react-query'
import { confidenceApi } from '../api/confidence-api'
import type { DocumentConfidenceData, ConfidenceSummary } from '../api/confidence-api'

// Query Keys
export const confidenceQueryKeys = {
    all: ['ocr-confidence'] as const,
    document: (documentId: string, page?: number) =>
        [...confidenceQueryKeys.all, 'document', documentId, page] as const,
    summary: (documentId: string) =>
        [...confidenceQueryKeys.all, 'summary', documentId] as const,
}

/**
 * Hook für detaillierte Confidence-Daten eines Dokuments.
 * Beinhaltet Wort-Level Daten mit Positionen.
 */
export function useDocumentConfidence(
    documentId: string | undefined,
    pageNumber?: number,
    enabled = true
) {
    return useQuery<DocumentConfidenceData>({
        queryKey: confidenceQueryKeys.document(documentId ?? '', pageNumber),
        queryFn: () => confidenceApi.getDocumentConfidence(documentId!, pageNumber),
        enabled: !!documentId && enabled,
        staleTime: 120000, // 2 Minuten (Confidence ändert sich selten)
        retry: 1,
    })
}

/**
 * Hook für schnelle Confidence-Zusammenfassung.
 */
export function useConfidenceSummary(
    documentId: string | undefined,
    enabled = true
) {
    return useQuery<ConfidenceSummary>({
        queryKey: confidenceQueryKeys.summary(documentId ?? ''),
        queryFn: () => confidenceApi.getConfidenceSummary(documentId!),
        enabled: !!documentId && enabled,
        staleTime: 120000,
        retry: 1,
    })
}
