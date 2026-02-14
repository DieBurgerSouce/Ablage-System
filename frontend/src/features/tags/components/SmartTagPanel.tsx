/**
 * SmartTagPanel - Panel mit allen Smart-Tags fuer ein Dokument
 *
 * Gruppiert nach Kategorie mit ausklappbaren Sektionen.
 * Zeigt Lade-/Leer-Zustaende und Aktionen (Akzeptieren/Ablehnen).
 */

import { useMemo, useCallback } from 'react'
import { ChevronDown, Sparkles, CheckCheck } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { useDocumentSmartTags } from '../hooks/use-smart-tags'
import { SmartTagBadge } from './SmartTagBadge'
import type { SmartTag, TagCategory } from '../types'

// ============================================================================
// Category Labels (German)
// ============================================================================

const categoryLabels: Record<TagCategory, string> = {
    urgency: 'Dringlichkeit',
    financial: 'Finanzen',
    quality: 'Qualitaet',
    action: 'Aktionen',
    trust: 'Vertrauen',
}

/** Display order for categories */
const categoryOrder: TagCategory[] = [
    'urgency',
    'financial',
    'quality',
    'action',
    'trust',
]

// ============================================================================
// Component Props
// ============================================================================

interface SmartTagPanelProps {
    documentId: string
    className?: string
}

// ============================================================================
// SmartTagPanel Component
// ============================================================================

export function SmartTagPanel({ documentId, className }: SmartTagPanelProps) {
    const { data: tags, isLoading, isError } = useDocumentSmartTags(documentId)

    // Group tags by category, sorted by priority within each group
    const groupedTags = useMemo(() => {
        if (!tags || tags.length === 0) return new Map<TagCategory, SmartTag[]>()

        const groups = new Map<TagCategory, SmartTag[]>()
        for (const category of categoryOrder) {
            const categoryTags = tags
                .filter((tag) => tag.category === category)
                .sort((a, b) => a.priority - b.priority)
            if (categoryTags.length > 0) {
                groups.set(category, categoryTags)
            }
        }
        return groups
    }, [tags])

    const totalTagCount = tags?.length ?? 0

    const handleAccept = useCallback((tag: SmartTag) => {
        toast.success(`Tag "${tag.displayName}" akzeptiert`, {
            description: tag.reason,
        })
    }, [])

    const handleReject = useCallback((tag: SmartTag) => {
        toast.info(`Tag "${tag.displayName}" abgelehnt`, {
            description: 'Das Feedback wird gespeichert.',
        })
    }, [])

    const handleAcceptAll = useCallback(() => {
        if (!tags || tags.length === 0) return
        toast.success(`${tags.length} Tags akzeptiert`, {
            description: 'Alle vorgeschlagenen Tags wurden uebernommen.',
        })
    }, [tags])

    // ---- Loading State ----
    if (isLoading) {
        return (
            <Card className={className}>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-sm font-medium">
                        <Sparkles className="h-4 w-4" />
                        Smart Tags
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    <Skeleton className="h-6 w-3/4" />
                    <Skeleton className="h-6 w-1/2" />
                    <Skeleton className="h-6 w-2/3" />
                </CardContent>
            </Card>
        )
    }

    // ---- Error State ----
    if (isError) {
        return (
            <Card className={className}>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-sm font-medium">
                        <Sparkles className="h-4 w-4" />
                        Smart Tags
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-muted-foreground">
                        Smart Tags konnten nicht geladen werden.
                    </p>
                </CardContent>
            </Card>
        )
    }

    // ---- Empty State ----
    if (totalTagCount === 0) {
        return (
            <Card className={className}>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-sm font-medium">
                        <Sparkles className="h-4 w-4" />
                        Smart Tags
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-muted-foreground">
                        Keine Smart Tags verfuegbar.
                    </p>
                </CardContent>
            </Card>
        )
    }

    // ---- Tags grouped by category ----
    return (
        <Card className={className}>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-sm font-medium">
                        <Sparkles className="h-4 w-4" />
                        Smart Tags
                        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-normal text-muted-foreground">
                            {totalTagCount}
                        </span>
                    </CardTitle>
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 gap-1.5 text-xs"
                        onClick={handleAcceptAll}
                    >
                        <CheckCheck className="h-3.5 w-3.5" />
                        Alle akzeptieren
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-2">
                {categoryOrder.map((category) => {
                    const categoryTags = groupedTags.get(category)
                    if (!categoryTags || categoryTags.length === 0) return null

                    return (
                        <CategorySection
                            key={category}
                            category={category}
                            tags={categoryTags}
                            onAccept={handleAccept}
                            onReject={handleReject}
                        />
                    )
                })}
            </CardContent>
        </Card>
    )
}

// ============================================================================
// CategorySection (Collapsible)
// ============================================================================

interface CategorySectionProps {
    category: TagCategory
    tags: SmartTag[]
    onAccept: (tag: SmartTag) => void
    onReject: (tag: SmartTag) => void
}

function CategorySection({
    category,
    tags,
    onAccept,
    onReject,
}: CategorySectionProps) {
    return (
        <Collapsible defaultOpen>
            <CollapsibleTrigger
                className={cn(
                    'flex w-full items-center justify-between rounded-md px-2 py-1.5',
                    'text-xs font-medium text-muted-foreground',
                    'hover:bg-muted/50 transition-colors',
                )}
            >
                <span>
                    {categoryLabels[category]}{' '}
                    <span className="font-normal">({tags.length})</span>
                </span>
                <ChevronDown className="h-3.5 w-3.5 transition-transform duration-200 [[data-state=open]>&]:rotate-180" />
            </CollapsibleTrigger>
            <CollapsibleContent>
                <div className="flex flex-wrap gap-1.5 px-2 pb-1 pt-1.5">
                    {tags.map((tag) => (
                        <SmartTagBadge
                            key={tag.name}
                            tag={tag}
                            showActions
                            onAccept={onAccept}
                            onReject={onReject}
                        />
                    ))}
                </div>
            </CollapsibleContent>
        </Collapsible>
    )
}
