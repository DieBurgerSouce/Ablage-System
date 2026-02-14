/**
 * SmartTagBadge - Einzelnes Smart-Tag mit Konfidenz, Icon und Erklaerung
 */

import * as React from 'react'
import {
    AlertTriangle,
    DollarSign,
    FileCheck,
    ArrowRight,
    Shield,
    Tag,
    Clock,
    TrendingUp,
    Star,
    AlertCircle,
    Ban,
    UserCheck,
    Check,
    X,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { SmartTag } from '../types'

// ============================================================================
// Icon Map
// ============================================================================

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
    AlertTriangle,
    DollarSign,
    FileCheck,
    ArrowRight,
    Shield,
    Tag,
    Clock,
    TrendingUp,
    Star,
    AlertCircle,
    Ban,
    UserCheck,
}

// ============================================================================
// Color Map (Light + Dark Mode)
// ============================================================================

const colorMap: Record<string, string> = {
    red: 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800',
    yellow: 'bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300 dark:border-yellow-800',
    green: 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800',
    blue: 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800',
    purple: 'bg-purple-100 text-purple-800 border-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-800',
    orange: 'bg-orange-100 text-orange-800 border-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:border-orange-800',
    gray: 'bg-gray-100 text-gray-800 border-gray-200 dark:bg-gray-900/30 dark:text-gray-300 dark:border-gray-800',
}

// ============================================================================
// Confidence Dot Color
// ============================================================================

function getConfidenceDotColor(confidence: number): string {
    if (confidence >= 0.9) return 'bg-green-500'
    if (confidence >= 0.7) return 'bg-yellow-500'
    return 'bg-red-500'
}

// ============================================================================
// Component Props
// ============================================================================

interface SmartTagBadgeProps {
    tag: SmartTag
    onAccept?: (tag: SmartTag) => void
    onReject?: (tag: SmartTag) => void
    showActions?: boolean
    className?: string
}

// ============================================================================
// SmartTagBadge Component
// ============================================================================

export function SmartTagBadge({
    tag,
    onAccept,
    onReject,
    showActions = false,
    className,
}: SmartTagBadgeProps) {
    const IconComponent = iconMap[tag.icon] ?? Tag
    const colorClass = colorMap[tag.color] ?? colorMap.gray
    const confidencePct = Math.round(tag.confidence * 100)

    return (
        <TooltipProvider delayDuration={300}>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div className={cn('inline-flex items-center gap-1', className)}>
                        <Badge
                            variant="outline"
                            className={cn(
                                colorClass,
                                'gap-1.5 py-1 pl-2 pr-2 text-xs font-medium',
                                showActions && 'pr-1',
                            )}
                        >
                            <IconComponent className="h-3 w-3 shrink-0" />
                            <span>{tag.displayName}</span>
                            <span
                                className={cn(
                                    'ml-0.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full',
                                    getConfidenceDotColor(tag.confidence),
                                )}
                                title={`${confidencePct}% Konfidenz`}
                            />
                            {showActions && (
                                <span className="ml-0.5 inline-flex items-center gap-0.5">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-4 w-4 rounded-full p-0 hover:bg-green-200 dark:hover:bg-green-800"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            onAccept?.(tag)
                                        }}
                                        aria-label={`Tag "${tag.displayName}" akzeptieren`}
                                    >
                                        <Check className="h-2.5 w-2.5" />
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-4 w-4 rounded-full p-0 hover:bg-red-200 dark:hover:bg-red-800"
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            onReject?.(tag)
                                        }}
                                        aria-label={`Tag "${tag.displayName}" ablehnen`}
                                    >
                                        <X className="h-2.5 w-2.5" />
                                    </Button>
                                </span>
                            )}
                        </Badge>
                    </div>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                    <p className="text-sm font-medium">{tag.displayName}</p>
                    <p className="text-xs text-muted-foreground">{tag.reason}</p>
                    <p className="mt-1 text-xs font-medium">
                        Konfidenz: {confidencePct}%
                    </p>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    )
}
