/**
 * DailyReviewBatch - Tabelle fuer KI-Entscheidungen die geprueft werden muessen
 *
 * Zeigt offene Review-Items mit Batch-Operationen (alle akzeptieren/ablehnen).
 * Verwendet shadcn Table + Checkbox Komponenten.
 */

import { useState, useCallback, useMemo } from 'react'
import { Check, X, PartyPopper, Brain } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { useReviewBatch, useReviewDecision } from '../hooks/use-auto-learning'
import type { AIDecision } from '../types'

// ==================== Constants ====================

const decisionTypeLabels: Record<string, string> = {
    categorization: 'Kategorisierung',
    entity_linking: 'Entity-Verknuepfung',
    smart_tagging: 'Smart Tagging',
    routing: 'Routing',
    invoice_approval: 'Rechnungsfreigabe',
    payment_matching: 'Zahlungszuordnung',
    ocr_correction: 'OCR-Korrektur',
}

// ==================== Helpers ====================

function getDecisionTypeLabel(type: string): string {
    return decisionTypeLabels[type] || type
}

function getConfidenceBadge(confidence: number) {
    const percent = Math.round(confidence * 100)
    if (confidence >= 0.9) {
        return <Badge variant="default" className="bg-green-600 text-xs">{percent}%</Badge>
    }
    if (confidence >= 0.7) {
        return <Badge variant="default" className="bg-yellow-600 text-xs">{percent}%</Badge>
    }
    return <Badge variant="destructive" className="text-xs">{percent}%</Badge>
}

function getExplanationText(decision: AIDecision): string {
    if (!decision.explanation) return '-'
    const reason = decision.explanation.reason as string | undefined
    if (reason) return reason
    // Fallback: Stringify relevant fields
    const entries = Object.entries(decision.explanation)
        .filter(([key]) => key !== 'metadata')
        .map(([key, val]) => `${key}: ${String(val)}`)
    return entries.length > 0 ? entries.join(', ') : '-'
}

function getDocumentLabel(decision: AIDecision): string {
    const value = decision.decisionValue
    const filename = value.filename as string | undefined
    if (filename) return filename
    if (decision.documentId) return decision.documentId.slice(0, 8) + '...'
    return '-'
}

// ==================== Skeleton Rows ====================

function SkeletonRows() {
    return (
        <>
            {Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                    <TableCell><Skeleton className="h-4 w-4" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-28" /></TableCell>
                    <TableCell><Skeleton className="h-5 w-12" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-40" /></TableCell>
                    <TableCell><Skeleton className="h-8 w-20" /></TableCell>
                </TableRow>
            ))}
        </>
    )
}

// ==================== Main Component ====================

export function DailyReviewBatch() {
    const { data: decisions, isLoading } = useReviewBatch()
    const reviewMutation = useReviewDecision()
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

    const allIds = useMemo(
        () => new Set((decisions || []).map((d) => d.id)),
        [decisions]
    )

    const isAllSelected = useMemo(
        () => allIds.size > 0 && allIds.size === selectedIds.size,
        [allIds, selectedIds]
    )

    const isSomeSelected = useMemo(
        () => selectedIds.size > 0 && selectedIds.size < allIds.size,
        [allIds, selectedIds]
    )

    // ---- Selection handlers ----

    const toggleSelect = useCallback((id: string) => {
        setSelectedIds((prev) => {
            const next = new Set(prev)
            if (next.has(id)) {
                next.delete(id)
            } else {
                next.add(id)
            }
            return next
        })
    }, [])

    const toggleSelectAll = useCallback(() => {
        if (isAllSelected) {
            setSelectedIds(new Set())
        } else {
            setSelectedIds(new Set(allIds))
        }
    }, [isAllSelected, allIds])

    // ---- Review handlers ----

    const handleReview = useCallback(
        async (decisionId: string, action: 'approved' | 'rejected') => {
            try {
                await reviewMutation.mutateAsync({
                    decisionId,
                    payload: { action },
                })
                setSelectedIds((prev) => {
                    const next = new Set(prev)
                    next.delete(decisionId)
                    return next
                })
                toast.success(
                    action === 'approved'
                        ? 'Entscheidung akzeptiert'
                        : 'Entscheidung abgelehnt'
                )
            } catch {
                toast.error('Pruefung fehlgeschlagen')
            }
        },
        [reviewMutation]
    )

    const handleBatchReview = useCallback(
        async (action: 'approved' | 'rejected') => {
            if (selectedIds.size === 0) return

            const ids = Array.from(selectedIds)
            let successCount = 0
            let failCount = 0

            for (const id of ids) {
                try {
                    await reviewMutation.mutateAsync({
                        decisionId: id,
                        payload: { action },
                    })
                    successCount++
                } catch {
                    failCount++
                }
            }

            setSelectedIds(new Set())

            if (successCount > 0) {
                toast.success(
                    `${successCount} Entscheidung${successCount > 1 ? 'en' : ''} ${
                        action === 'approved' ? 'akzeptiert' : 'abgelehnt'
                    }`
                )
            }
            if (failCount > 0) {
                toast.error(`${failCount} Pruefung${failCount > 1 ? 'en' : ''} fehlgeschlagen`)
            }
        },
        [selectedIds, reviewMutation]
    )

    // ---- Empty state ----

    if (!isLoading && (!decisions || decisions.length === 0)) {
        return (
            <div className="flex flex-col items-center justify-center py-16 text-center">
                <PartyPopper className="h-12 w-12 text-muted-foreground/40 mb-4" />
                <h3 className="text-lg font-semibold mb-1">
                    Keine offenen Pruefungen
                </h3>
                <p className="text-sm text-muted-foreground">
                    Alles erledigt! Die KI hat alle Aktionen zuverlaessig verarbeitet.
                </p>
            </div>
        )
    }

    return (
        <div className="space-y-4">
            {/* Header mit Batch-Operationen */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Brain className="h-5 w-5 text-muted-foreground" />
                    <h3 className="text-lg font-semibold">
                        KI-Pruefungen
                    </h3>
                    {decisions && (
                        <Badge variant="secondary">
                            {decisions.length} offen
                        </Badge>
                    )}
                </div>
                {selectedIds.size > 0 && (
                    <div className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground">
                            {selectedIds.size} ausgewaehlt
                        </span>
                        <Button
                            size="sm"
                            variant="default"
                            onClick={() => handleBatchReview('approved')}
                            disabled={reviewMutation.isPending}
                        >
                            <Check className="h-4 w-4 mr-1" />
                            Ausgewaehlte akzeptieren
                        </Button>
                        <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => handleBatchReview('rejected')}
                            disabled={reviewMutation.isPending}
                        >
                            <X className="h-4 w-4 mr-1" />
                            Ausgewaehlte ablehnen
                        </Button>
                    </div>
                )}
            </div>

            {/* Tabelle */}
            <div className="rounded-md border">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead className="w-[40px]">
                                <Checkbox
                                    checked={isAllSelected}
                                    onCheckedChange={toggleSelectAll}
                                    aria-label="Alle auswaehlen"
                                    {...(isSomeSelected ? { 'data-state': 'indeterminate' } : {})}
                                />
                            </TableHead>
                            <TableHead>Dokument</TableHead>
                            <TableHead>Aktionstyp</TableHead>
                            <TableHead>Konfidenz</TableHead>
                            <TableHead>KI-Erklaerung</TableHead>
                            <TableHead className="text-right">Aktionen</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {isLoading && <SkeletonRows />}

                        {!isLoading &&
                            decisions?.map((decision) => (
                                <TableRow
                                    key={decision.id}
                                    className={cn(
                                        selectedIds.has(decision.id) && 'bg-muted/50'
                                    )}
                                >
                                    <TableCell>
                                        <Checkbox
                                            checked={selectedIds.has(decision.id)}
                                            onCheckedChange={() => toggleSelect(decision.id)}
                                            aria-label={`Entscheidung ${decision.id} auswaehlen`}
                                        />
                                    </TableCell>
                                    <TableCell className="font-medium max-w-[150px] truncate">
                                        {getDocumentLabel(decision)}
                                    </TableCell>
                                    <TableCell>
                                        <Badge variant="outline">
                                            {getDecisionTypeLabel(decision.decisionType)}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>
                                        {getConfidenceBadge(decision.confidence)}
                                    </TableCell>
                                    <TableCell className="max-w-[250px] truncate text-sm text-muted-foreground">
                                        {getExplanationText(decision)}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <div className="flex items-center justify-end gap-1">
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-8 w-8 p-0 text-green-600 hover:text-green-700 hover:bg-green-50"
                                                onClick={() =>
                                                    handleReview(decision.id, 'approved')
                                                }
                                                disabled={reviewMutation.isPending}
                                                title="Akzeptieren"
                                            >
                                                <Check className="h-4 w-4" />
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
                                                onClick={() =>
                                                    handleReview(decision.id, 'rejected')
                                                }
                                                disabled={reviewMutation.isPending}
                                                title="Ablehnen"
                                            >
                                                <X className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ))}
                    </TableBody>
                </Table>
            </div>
        </div>
    )
}
