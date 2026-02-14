/**
 * TanStack Query Hooks fuer Batch-OCR-Korrektur Feature
 */

import { useState, useCallback, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ocrBatchApi } from '../api/ocr-batch-api'
import type {
    BatchFilterState,
    ConfidenceRange,
    BatchCorrectionPayload,
    OcrBatchDocument,
} from '../types'

// ============================================================================
// Query Keys
// ============================================================================

export const batchQueryKeys = {
    all: ['ocr-batch'] as const,
    documents: (filters: BatchFilterState) =>
        [...batchQueryKeys.all, 'documents', filters] as const,
    extractedFields: (docId: string) =>
        [...batchQueryKeys.all, 'fields', docId] as const,
}

// ============================================================================
// Confidence Range -> max value mapping
// ============================================================================

function confidenceRangeToMax(range: ConfidenceRange): number | undefined {
    switch (range) {
        case 'low': return 0.70
        case 'medium': return 0.85
        case 'high': return 0.95
        case 'all': return undefined
    }
}

// ============================================================================
// Hook: Batch Documents List
// ============================================================================

export function useOcrBatchDocuments(filters: BatchFilterState) {
    return useQuery({
        queryKey: batchQueryKeys.documents(filters),
        queryFn: () =>
            ocrBatchApi.getLowConfidenceDocuments({
                page: filters.page,
                per_page: filters.perPage,
                document_type: filters.documentType === 'all' ? undefined : filters.documentType,
                confidence_max: confidenceRangeToMax(filters.confidenceRange),
                status: filters.status === 'all' ? 'completed' : filters.status,
                sort_by: 'ocr_confidence',
                sort_order: 'asc',
            }),
        staleTime: 30000, // 30 Sekunden
        placeholderData: (prev) => prev,
    })
}

// ============================================================================
// Hook: Extracted Fields for a Document
// ============================================================================

export function useDocumentExtractedFields(documentId: string | null) {
    return useQuery({
        queryKey: batchQueryKeys.extractedFields(documentId ?? ''),
        queryFn: () => ocrBatchApi.getDocumentExtractedFields(documentId!),
        enabled: !!documentId,
        staleTime: 60000,
    })
}

// ============================================================================
// Hook: Save Corrections Mutation
// ============================================================================

export function useSaveCorrections() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (payload: BatchCorrectionPayload) =>
            ocrBatchApi.saveCorrections(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: batchQueryKeys.all })
        },
    })
}

// ============================================================================
// Hook: Batch Confirm Mutation
// ============================================================================

export function useBatchConfirm() {
    const queryClient = useQueryClient()

    return useMutation({
        mutationFn: (documentIds: string[]) =>
            ocrBatchApi.confirmDocuments({ document_ids: documentIds }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: batchQueryKeys.all })
        },
    })
}

// ============================================================================
// Hook: Batch Selection + Review Tracking
// ============================================================================

export function useOcrBatchSelection() {
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
    const [reviewedIds, setReviewedIds] = useState<Set<string>>(new Set())
    const [expandedId, setExpandedId] = useState<string | null>(null)

    const toggleSelection = useCallback((id: string) => {
        setSelectedIds(prev => {
            const next = new Set(prev)
            if (next.has(id)) {
                next.delete(id)
            } else {
                next.add(id)
            }
            return next
        })
    }, [])

    const selectAll = useCallback((docs: OcrBatchDocument[]) => {
        setSelectedIds(new Set(docs.map(d => d.id)))
    }, [])

    const deselectAll = useCallback(() => {
        setSelectedIds(new Set())
    }, [])

    const toggleSelectAll = useCallback((docs: OcrBatchDocument[]) => {
        setSelectedIds(prev => {
            if (prev.size === docs.length) {
                return new Set()
            }
            return new Set(docs.map(d => d.id))
        })
    }, [])

    const markReviewed = useCallback((id: string) => {
        setReviewedIds(prev => {
            const next = new Set(prev)
            next.add(id)
            return next
        })
    }, [])

    const toggleExpanded = useCallback((id: string) => {
        setExpandedId(prev => prev === id ? null : id)
    }, [])

    const isSelected = useCallback((id: string) => selectedIds.has(id), [selectedIds])
    const isReviewed = useCallback((id: string) => reviewedIds.has(id), [reviewedIds])

    const selectedCount = useMemo(() => selectedIds.size, [selectedIds])
    const reviewedCount = useMemo(() => reviewedIds.size, [reviewedIds])
    const selectedArray = useMemo(() => Array.from(selectedIds), [selectedIds])

    return {
        selectedIds,
        reviewedIds,
        expandedId,
        toggleSelection,
        selectAll,
        deselectAll,
        toggleSelectAll,
        markReviewed,
        toggleExpanded,
        isSelected,
        isReviewed,
        selectedCount,
        reviewedCount,
        selectedArray,
    }
}
