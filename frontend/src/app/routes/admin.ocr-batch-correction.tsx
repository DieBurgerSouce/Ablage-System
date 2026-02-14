/**
 * Batch-OCR-Korrektur Admin Route
 *
 * Erlaubt die Korrektur mehrerer OCR-Ergebnisse auf einmal.
 * Filtert nach niedrigem Confidence, Dokumenttyp und Status.
 */

import { useState, useCallback } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { FileCheck2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
    OcrBatchCorrectionTable,
    OcrBatchToolbar,
    useOcrBatchDocuments,
    useOcrBatchSelection,
    useBatchConfirm,
} from '@/features/ocr-batch'
import type { BatchFilterState, ConfidenceRange } from '@/features/ocr-batch'

export const Route = createFileRoute('/admin/ocr-batch-correction')({
    component: OcrBatchCorrectionPage,
})

function OcrBatchCorrectionPage() {
    // Filter state
    const [filters, setFilters] = useState<BatchFilterState>({
        documentType: 'all',
        confidenceRange: 'medium' as ConfidenceRange,
        status: 'all',
        page: 1,
        perPage: 20,
    })

    // Query
    const { data, isLoading } = useOcrBatchDocuments(filters)

    // Selection & review tracking
    const {
        selectedIds,
        reviewedIds,
        expandedId,
        toggleSelection,
        toggleSelectAll,
        toggleExpanded,
        markReviewed,
        selectedCount,
        reviewedCount,
        selectedArray,
    } = useOcrBatchSelection()

    // Batch confirm mutation
    const batchConfirm = useBatchConfirm()

    const documents = data?.items ?? []
    const totalCount = data?.total ?? 0
    const totalPages = Math.ceil(totalCount / filters.perPage) || 1

    // Filter change handler
    const handleFilterChange = useCallback((partial: Partial<BatchFilterState>) => {
        setFilters(prev => ({ ...prev, ...partial }))
    }, [])

    // Page change
    const handlePageChange = useCallback((page: number) => {
        setFilters(prev => ({ ...prev, page }))
    }, [])

    // Batch confirm selected
    const handleBatchConfirm = useCallback(async () => {
        if (selectedArray.length === 0) return
        await batchConfirm.mutateAsync(selectedArray)
        // Mark all selected as reviewed
        selectedArray.forEach(id => markReviewed(id))
    }, [selectedArray, batchConfirm, markReviewed])

    return (
        <div className="space-y-6">
            {/* Page header */}
            <div>
                <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
                    <FileCheck2 className="h-6 w-6" />
                    Batch-OCR-Korrektur
                </h1>
                <p className="text-muted-foreground mt-1">
                    Ueberpruefen und korrigieren Sie OCR-Ergebnisse mit niedriger Konfidenz gesammelt.
                </p>
            </div>

            {/* Main card */}
            <Card>
                <CardHeader className="pb-4">
                    <CardTitle>Dokumente zur Korrektur</CardTitle>
                    <CardDescription>
                        {totalCount} Dokumente mit niedrigem OCR-Confidence gefunden. Sortiert nach Konfidenz (niedrigste zuerst).
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* Toolbar: filters + selection */}
                    <OcrBatchToolbar
                        filters={filters}
                        onFilterChange={handleFilterChange}
                        totalCount={totalCount}
                        reviewedCount={reviewedCount}
                        selectedCount={selectedCount}
                        allSelected={documents.length > 0 && selectedIds.size === documents.length}
                        onToggleSelectAll={() => toggleSelectAll(documents)}
                        onBatchConfirm={handleBatchConfirm}
                        isBatchConfirming={batchConfirm.isPending}
                    />

                    {/* Table */}
                    <OcrBatchCorrectionTable
                        documents={documents}
                        isLoading={isLoading}
                        selectedIds={selectedIds}
                        reviewedIds={reviewedIds}
                        expandedId={expandedId}
                        onToggleSelection={toggleSelection}
                        onToggleExpanded={toggleExpanded}
                        onMarkReviewed={markReviewed}
                        page={filters.page}
                        totalPages={totalPages}
                        onPageChange={handlePageChange}
                    />
                </CardContent>
            </Card>
        </div>
    )
}
