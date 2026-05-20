/**
 * OcrBatchToolbar - Filter, Auswahl und Batch-Aktionen
 *
 * Enthaelt:
 * - Filter: Dokumenttyp, Konfidenz-Bereich, Status
 * - Alle-auswaehlen Checkbox
 * - Fortschrittsanzeige
 * - Batch-Aktionen
 */

import { CheckSquare, Filter } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import type { BatchFilterState, ConfidenceRange } from '../types'

interface OcrBatchToolbarProps {
    filters: BatchFilterState
    onFilterChange: (filters: Partial<BatchFilterState>) => void
    totalCount: number
    reviewedCount: number
    selectedCount: number
    allSelected: boolean
    onToggleSelectAll: () => void
    onBatchConfirm: () => void
    isBatchConfirming: boolean
}

export function OcrBatchToolbar({
    filters,
    onFilterChange,
    totalCount,
    reviewedCount,
    selectedCount,
    allSelected,
    onToggleSelectAll,
    onBatchConfirm,
    isBatchConfirming,
}: OcrBatchToolbarProps) {
    const progressPct = totalCount > 0 ? Math.round((reviewedCount / totalCount) * 100) : 0

    return (
        <div className="space-y-3">
            {/* Filter row */}
            <div className="flex flex-wrap items-center gap-3">
                <Filter className="h-4 w-4 text-muted-foreground shrink-0" />

                <Select
                    value={filters.documentType}
                    onValueChange={(v) => onFilterChange({ documentType: v, page: 1 })}
                >
                    <SelectTrigger className="w-[160px]">
                        <SelectValue placeholder="Dokumenttyp" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Alle Typen</SelectItem>
                        <SelectItem value="invoice">Rechnung</SelectItem>
                        <SelectItem value="delivery_note">Lieferschein</SelectItem>
                        <SelectItem value="order_confirmation">Auftragsbestaetigung</SelectItem>
                        <SelectItem value="contract">Vertrag</SelectItem>
                        <SelectItem value="letter">Brief</SelectItem>
                        <SelectItem value="other">Sonstige</SelectItem>
                    </SelectContent>
                </Select>

                <Select
                    value={filters.confidenceRange}
                    onValueChange={(v) => onFilterChange({ confidenceRange: v as ConfidenceRange, page: 1 })}
                >
                    <SelectTrigger className="w-[160px]">
                        <SelectValue placeholder="Konfidenz" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Alle Konfidenzen</SelectItem>
                        <SelectItem value="low">Niedrig (&lt; 70%)</SelectItem>
                        <SelectItem value="medium">Mittel (&lt; 85%)</SelectItem>
                        <SelectItem value="high">Hoch (&lt; 95%)</SelectItem>
                    </SelectContent>
                </Select>

                <Select
                    value={filters.status}
                    onValueChange={(v) => onFilterChange({ status: v, page: 1 })}
                >
                    <SelectTrigger className="w-[160px]">
                        <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Alle Status</SelectItem>
                        <SelectItem value="completed">OCR abgeschlossen</SelectItem>
                        <SelectItem value="pending">Ausstehend</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {/* Selection + progress row */}
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        <Checkbox
                            id="select-all"
                            checked={allSelected}
                            onCheckedChange={onToggleSelectAll}
                        />
                        <label
                            htmlFor="select-all"
                            className="text-sm font-medium cursor-pointer"
                        >
                            Alle auswaehlen
                        </label>
                    </div>

                    <div className="text-sm text-muted-foreground">
                        {reviewedCount} von {totalCount} ueberprueft
                    </div>

                    <div className="w-32">
                        <Progress value={progressPct} className="h-2" />
                    </div>
                </div>

                {selectedCount > 0 && (
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={onBatchConfirm}
                        disabled={isBatchConfirming}
                    >
                        <CheckSquare className="h-4 w-4 mr-1.5" />
                        {isBatchConfirming
                            ? 'Bestaetigen...'
                            : `${selectedCount} als korrekt markieren`
                        }
                    </Button>
                )}
            </div>
        </div>
    )
}
