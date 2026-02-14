/**
 * OcrBatchCorrectionTable - Haupttabelle fuer Batch-OCR-Korrektur
 *
 * TanStack Table mit:
 * - Checkbox-Spalte fuer Multi-Select
 * - Expandierbare Zeilen fuer Inline-Editing
 * - Sortierung nach Konfidenz (niedrigste zuerst)
 * - Pagination (20 pro Seite)
 */

import { Fragment, useMemo, useCallback } from 'react'
import {
    useReactTable,
    getCoreRowModel,
    getSortedRowModel,
    flexRender,
    createColumnHelper,
    type SortingState,
} from '@tanstack/react-table'
import {
    FileText,
    Eye,
    ChevronDown,
    ChevronRight,
    Clock,
    CheckCircle2,
    Loader2,
} from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { OcrBatchDocument } from '../types'
import { OcrConfidenceBadge } from './OcrConfidenceBadge'
import { OcrFieldEditor } from './OcrFieldEditor'

const columnHelper = createColumnHelper<OcrBatchDocument>()

// Status-Konfiguration
const statusConfig: Record<string, {
    label: string
    icon: typeof Clock
    className: string
}> = {
    pending: {
        label: 'Ausstehend',
        icon: Clock,
        className: 'text-yellow-600 dark:text-yellow-400',
    },
    reviewed: {
        label: 'Geprueft',
        icon: CheckCircle2,
        className: 'text-green-600 dark:text-green-400',
    },
    corrected: {
        label: 'Korrigiert',
        icon: CheckCircle2,
        className: 'text-blue-600 dark:text-blue-400',
    },
    confirmed: {
        label: 'Bestaetigt',
        icon: CheckCircle2,
        className: 'text-green-600 dark:text-green-400',
    },
}

// Document type labels
const docTypeLabels: Record<string, string> = {
    invoice: 'Rechnung',
    delivery_note: 'Lieferschein',
    order_confirmation: 'Auftr.best.',
    contract: 'Vertrag',
    letter: 'Brief',
    other: 'Sonstige',
}

interface OcrBatchCorrectionTableProps {
    documents: OcrBatchDocument[]
    isLoading: boolean
    selectedIds: Set<string>
    reviewedIds: Set<string>
    expandedId: string | null
    onToggleSelection: (id: string) => void
    onToggleExpanded: (id: string) => void
    onMarkReviewed: (id: string) => void
    page: number
    totalPages: number
    onPageChange: (page: number) => void
}

export function OcrBatchCorrectionTable({
    documents,
    isLoading,
    selectedIds,
    reviewedIds,
    expandedId,
    onToggleSelection,
    onToggleExpanded,
    onMarkReviewed,
    page,
    totalPages,
    onPageChange,
}: OcrBatchCorrectionTableProps) {
    const [sorting, setSorting] = useState<SortingState>([
        { id: 'ocr_confidence', desc: false },
    ])

    const handleSaved = useCallback((docId: string) => {
        onMarkReviewed(docId)
        onToggleExpanded(docId)
    }, [onMarkReviewed, onToggleExpanded])

    const handleSkip = useCallback((docId: string) => {
        onToggleExpanded(docId)
    }, [onToggleExpanded])

    const handleConfirmCorrect = useCallback((docId: string) => {
        onMarkReviewed(docId)
        onToggleExpanded(docId)
    }, [onMarkReviewed, onToggleExpanded])

    const columns = useMemo(() => [
        // Checkbox column
        columnHelper.display({
            id: 'select',
            header: () => null,
            cell: ({ row }) => (
                <Checkbox
                    checked={selectedIds.has(row.original.id)}
                    onCheckedChange={() => onToggleSelection(row.original.id)}
                    aria-label={`${row.original.filename} auswaehlen`}
                />
            ),
            size: 40,
        }),

        // Filename
        columnHelper.accessor('filename', {
            header: 'Datei',
            cell: (info) => (
                <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span className="font-medium truncate max-w-[200px]" title={info.getValue()}>
                        {info.getValue()}
                    </span>
                </div>
            ),
        }),

        // Document type
        columnHelper.accessor('document_type', {
            header: 'Typ',
            cell: (info) => (
                <Badge variant="outline">
                    {docTypeLabels[info.getValue()] || info.getValue()}
                </Badge>
            ),
        }),

        // OCR Confidence
        columnHelper.accessor('ocr_confidence', {
            header: 'Konfidenz',
            cell: (info) => (
                <OcrConfidenceBadge confidence={info.getValue()} />
            ),
        }),

        // Status
        columnHelper.display({
            id: 'review_status',
            header: 'Status',
            cell: ({ row }) => {
                const isReviewed = reviewedIds.has(row.original.id)
                const config = isReviewed
                    ? statusConfig.reviewed
                    : statusConfig.pending
                const Icon = config.icon
                return (
                    <div className={cn('flex items-center gap-1.5 text-sm', config.className)}>
                        <Icon className="h-4 w-4" />
                        <span>{config.label}</span>
                    </div>
                )
            },
        }),

        // Actions
        columnHelper.display({
            id: 'actions',
            header: 'Aktion',
            cell: ({ row }) => {
                const isExpanded = expandedId === row.original.id
                const isReviewed = reviewedIds.has(row.original.id)
                return (
                    <Button
                        variant={isExpanded ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => onToggleExpanded(row.original.id)}
                    >
                        {isExpanded ? (
                            <>
                                <ChevronDown className="h-4 w-4 mr-1" />
                                Schliessen
                            </>
                        ) : (
                            <>
                                {isReviewed ? (
                                    <Eye className="h-4 w-4 mr-1" />
                                ) : (
                                    <ChevronRight className="h-4 w-4 mr-1" />
                                )}
                                {isReviewed ? 'Ansehen' : 'Pruefen'}
                            </>
                        )}
                    </Button>
                )
            },
        }),
    ], [selectedIds, reviewedIds, expandedId, onToggleSelection, onToggleExpanded])

    const table = useReactTable({
        data: documents,
        columns,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
        onSortingChange: setSorting,
        state: { sorting },
        manualPagination: true,
    })

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-48">
                <div className="flex items-center gap-3 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    <span>Lade Dokumente...</span>
                </div>
            </div>
        )
    }

    if (documents.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
                <FileText className="h-12 w-12 mb-3 opacity-30" />
                <p className="text-lg font-medium">Keine Dokumente gefunden</p>
                <p className="text-sm">Passen Sie die Filter an, um Dokumente anzuzeigen.</p>
            </div>
        )
    }

    return (
        <div className="space-y-4">
            <Table ariaLabel="Batch-OCR-Korrektur Tabelle">
                <TableHeader>
                    {table.getHeaderGroups().map((headerGroup) => (
                        <TableRow key={headerGroup.id}>
                            {headerGroup.headers.map((header) => (
                                <TableHead key={header.id}>
                                    {header.isPlaceholder
                                        ? null
                                        : flexRender(header.column.columnDef.header, header.getContext())}
                                </TableHead>
                            ))}
                        </TableRow>
                    ))}
                </TableHeader>
                <TableBody>
                    {table.getRowModel().rows.map((row) => (
                        <Fragment key={row.id}>
                            <TableRow
                                isSelected={selectedIds.has(row.original.id)}
                                className={cn(
                                    expandedId === row.original.id && 'bg-muted/30 border-b-0'
                                )}
                            >
                                {row.getVisibleCells().map((cell) => (
                                    <TableCell key={cell.id}>
                                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                    </TableCell>
                                ))}
                            </TableRow>

                            {/* Expanded row: Inline editor */}
                            {expandedId === row.original.id && (
                                <TableRow key={`${row.id}-expanded`}>
                                    <TableCell colSpan={columns.length} className="p-4 bg-muted/10">
                                        <OcrFieldEditor
                                            documentId={row.original.id}
                                            filename={row.original.filename}
                                            onSaved={() => handleSaved(row.original.id)}
                                            onSkip={() => handleSkip(row.original.id)}
                                            onConfirmCorrect={() => handleConfirmCorrect(row.original.id)}
                                            onClose={() => onToggleExpanded(row.original.id)}
                                        />
                                    </TableCell>
                                </TableRow>
                            )}
                        </Fragment>
                    ))}
                </TableBody>
            </Table>

            {/* Pagination */}
            <div className="flex items-center justify-between">
                <div className="text-sm text-muted-foreground">
                    Seite {page} von {totalPages || 1}
                </div>
                <div className="flex gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onPageChange(page - 1)}
                        disabled={page <= 1}
                    >
                        Zurueck
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onPageChange(page + 1)}
                        disabled={page >= totalPages}
                    >
                        Weiter
                    </Button>
                </div>
            </div>
        </div>
    )
}
