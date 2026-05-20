/**
 * OcrConfidenceBadge - Farbkodiertes Konfidenz-Badge
 *
 * Gruen (>= 90%): Hoch
 * Gelb (>= 70%): Mittel
 * Rot (< 70%): Niedrig
 */

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface OcrConfidenceBadgeProps {
    confidence: number
    showPercent?: boolean
    className?: string
}

function getConfidenceConfig(confidence: number): {
    label: string
    className: string
} {
    const pct = confidence * 100
    if (pct >= 90) {
        return {
            label: 'Hoch',
            className: 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800',
        }
    }
    if (pct >= 70) {
        return {
            label: 'Mittel',
            className: 'bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300 dark:border-yellow-800',
        }
    }
    return {
        label: 'Niedrig',
        className: 'bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800',
    }
}

export function OcrConfidenceBadge({
    confidence,
    showPercent = true,
    className,
}: OcrConfidenceBadgeProps) {
    const config = getConfidenceConfig(confidence)
    const pct = Math.round(confidence * 100)

    return (
        <Badge
            variant="outline"
            className={cn(config.className, className)}
        >
            {showPercent ? `${pct}%` : config.label}
        </Badge>
    )
}
