/**
 * RecentActionsPanel - Seitliches Panel mit letzten KI-Aktionen
 *
 * Zeigt automatisch angewandte KI-Entscheidungen in einem Sheet.
 * Jede Aktion kann per "Rueckgaengig"-Button zurueckgesetzt werden.
 */

import { Brain, Tags, Link, Route, Undo2 } from 'lucide-react'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { useGlobalUndo } from '@/hooks/useUndoableAction'
import { useRecentAutoActions, useReviewDecision } from '../hooks/use-auto-learning'
import type { AIDecision } from '../types'

// ==================== Props ====================

interface RecentActionsPanelProps {
    open: boolean
    onOpenChange: (open: boolean) => void
}

// ==================== Helpers ====================

/** Icon basierend auf Entscheidungstyp */
function getDecisionIcon(decisionType: string) {
    switch (decisionType) {
        case 'categorization':
            return Brain
        case 'smart_tagging':
            return Tags
        case 'entity_linking':
            return Link
        case 'routing':
            return Route
        default:
            return Brain
    }
}

/** Deutsche Beschreibung der KI-Aktion */
function getDecisionDescription(decision: AIDecision): string {
    const value = decision.decisionValue
    switch (decision.decisionType) {
        case 'categorization':
            return `Dokument als "${(value.display_name as string) || (value.category as string) || 'Unbekannt'}" kategorisiert`
        case 'entity_linking':
            return `Mit "${(value.entity_name as string) || 'Unbekannt'}" verknuepft`
        case 'smart_tagging':
            return `Tag "${(value.tag_name as string) || 'Unbekannt'}" zugewiesen`
        case 'routing':
            return `An "${(value.target_name as string) || 'Unbekannt'}" weitergeleitet`
        default:
            return `KI-Aktion: ${decision.decisionType}`
    }
}

/** Relative Zeitanzeige auf Deutsch */
function getRelativeTime(dateStr: string): string {
    const now = Date.now()
    const then = new Date(dateStr).getTime()
    const diffMs = now - then
    const diffMin = Math.floor(diffMs / 60_000)

    if (diffMin < 1) return 'Gerade eben'
    if (diffMin < 60) return `vor ${diffMin} Min.`

    const diffH = Math.floor(diffMin / 60)
    if (diffH < 24) return `vor ${diffH} Std.`

    const diffD = Math.floor(diffH / 24)
    if (diffD === 1) return 'vor 1 Tag'
    return `vor ${diffD} Tagen`
}

/** Farbe fuer Konfidenz-Badge */
function getConfidenceColor(confidence: number): string {
    if (confidence >= 0.9) return 'bg-green-500'
    if (confidence >= 0.7) return 'bg-yellow-500'
    return 'bg-red-500'
}

// ==================== Action Row ====================

function ActionRow({ decision }: { decision: AIDecision }) {
    const { executeAction } = useGlobalUndo()
    const reviewMutation = useReviewDecision()
    const Icon = getDecisionIcon(decision.decisionType)

    const handleUndo = async () => {
        await executeAction({
            description: 'KI-Aktion rueckgaengig gemacht',
            execute: async () => {
                await reviewMutation.mutateAsync({
                    decisionId: decision.id,
                    payload: { action: 'rejected', comment: 'Vom Benutzer rueckgaengig gemacht' },
                })
            },
            undo: async () => {
                // Re-approve if user undoes the undo
                await reviewMutation.mutateAsync({
                    decisionId: decision.id,
                    payload: { action: 'approved', comment: 'Rueckgaengig-Aktion widerrufen' },
                })
            },
        })
    }

    return (
        <div className="flex items-start gap-3 py-3 px-1 border-b border-border/50 last:border-b-0">
            <div className="mt-0.5 flex-shrink-0 rounded-md bg-muted p-2">
                <Icon className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="flex-1 min-w-0">
                <p className="text-sm font-medium leading-tight truncate">
                    {getDecisionDescription(decision)}
                </p>
                <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-muted-foreground">
                        {getRelativeTime(decision.createdAt)}
                    </span>
                    <div className="flex items-center gap-1">
                        <span
                            className={cn(
                                'inline-block h-2 w-2 rounded-full',
                                getConfidenceColor(decision.confidence)
                            )}
                        />
                        <span className="text-xs text-muted-foreground">
                            {Math.round(decision.confidence * 100)}%
                        </span>
                    </div>
                </div>
            </div>
            <Button
                variant="ghost"
                size="sm"
                className="flex-shrink-0 text-xs h-7 px-2"
                onClick={handleUndo}
                disabled={reviewMutation.isPending}
                title="Rueckgaengig"
            >
                <Undo2 className="h-3.5 w-3.5 mr-1" />
                Rueckgaengig
            </Button>
        </div>
    )
}

// ==================== Loading Skeleton ====================

function ActionSkeleton() {
    return (
        <div className="flex items-start gap-3 py-3 px-1">
            <Skeleton className="h-8 w-8 rounded-md flex-shrink-0" />
            <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/3" />
            </div>
            <Skeleton className="h-7 w-24 flex-shrink-0" />
        </div>
    )
}

// ==================== Main Component ====================

export function RecentActionsPanel({ open, onOpenChange }: RecentActionsPanelProps) {
    const { data: decisions, isLoading } = useRecentAutoActions()

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent side="right" className="flex flex-col p-0">
                <SheetHeader className="px-6 pt-6 pb-4 border-b">
                    <SheetTitle className="flex items-center gap-2">
                        <Brain className="h-5 w-5" />
                        Letzte KI-Aktionen
                    </SheetTitle>
                </SheetHeader>

                <ScrollArea className="flex-1 px-4">
                    {isLoading && (
                        <div className="space-y-0">
                            {Array.from({ length: 5 }).map((_, i) => (
                                <ActionSkeleton key={i} />
                            ))}
                        </div>
                    )}

                    {!isLoading && (!decisions || decisions.length === 0) && (
                        <div className="flex flex-col items-center justify-center py-12 text-center">
                            <Brain className="h-10 w-10 text-muted-foreground/40 mb-3" />
                            <p className="text-sm text-muted-foreground">
                                Keine automatischen Aktionen
                            </p>
                            <p className="text-xs text-muted-foreground/60 mt-1">
                                KI-Aktionen erscheinen hier sobald Dokumente verarbeitet werden
                            </p>
                        </div>
                    )}

                    {!isLoading && decisions && decisions.length > 0 && (
                        <div className="py-1">
                            {decisions.map((decision) => (
                                <ActionRow key={decision.id} decision={decision} />
                            ))}
                        </div>
                    )}
                </ScrollArea>

                {!isLoading && decisions && decisions.length > 0 && (
                    <div className="px-6 py-3 border-t">
                        <Badge variant="secondary" className="text-xs">
                            {decisions.length} Aktionen
                        </Badge>
                    </div>
                )}
            </SheetContent>
        </Sheet>
    )
}
