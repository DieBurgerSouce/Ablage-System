/**
 * FlagReasonBanner - Zeigt prominent warum ein Sample geflaggt wurde.
 *
 * Farbcodierung nach Severity:
 * - critical: Rot
 * - high: Orange
 * - medium: Gelb
 * - low: Grau
 */

import { AlertTriangle, AlertCircle, Info, Target, Shield, TrendingDown } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import type { FlagReason, FlagType } from '../types'

interface FlagReasonBannerProps {
    reasons: FlagReason[]
    className?: string
}

// Icons für Flag-Typen
const FLAG_ICONS: Record<FlagType, React.ElementType> = {
    coverage_gap: Target,
    low_confidence: TrendingDown,
    spot_check: Info,
    validation_error: AlertCircle,
    business_critical: Shield,
}

// Farben für Severity
const SEVERITY_STYLES = {
    critical: {
        variant: 'destructive' as const,
        bgClass: 'bg-red-50 dark:bg-red-950/30 border-red-300 dark:border-red-800',
        iconClass: 'text-red-600 dark:text-red-400',
        badgeVariant: 'destructive' as const,
    },
    high: {
        variant: 'default' as const,
        bgClass: 'bg-orange-50 dark:bg-orange-950/30 border-orange-300 dark:border-orange-800',
        iconClass: 'text-orange-600 dark:text-orange-400',
        badgeVariant: 'default' as const,
    },
    medium: {
        variant: 'default' as const,
        bgClass: 'bg-amber-50 dark:bg-amber-950/30 border-amber-300 dark:border-amber-800',
        iconClass: 'text-amber-600 dark:text-amber-400',
        badgeVariant: 'secondary' as const,
    },
    low: {
        variant: 'default' as const,
        bgClass: 'bg-slate-50 dark:bg-slate-950/30 border-slate-300 dark:border-slate-700',
        iconClass: 'text-slate-600 dark:text-slate-400',
        badgeVariant: 'outline' as const,
    },
}

export function FlagReasonBanner({ reasons, className }: FlagReasonBannerProps) {
    if (reasons.length === 0) {
        return null
    }

    // Sortiere nach Severity (critical zuerst)
    const sortedReasons = [...reasons].sort((a, b) => {
        const order = { critical: 0, high: 1, medium: 2, low: 3 }
        return order[a.severity] - order[b.severity]
    })

    // Höchste Severity bestimmt Gesamt-Style
    const highestSeverity = sortedReasons[0].severity
    const styles = SEVERITY_STYLES[highestSeverity]

    // Mehrere Gründe kompakt anzeigen
    if (sortedReasons.length === 1) {
        const reason = sortedReasons[0]
        const Icon = FLAG_ICONS[reason.type]

        return (
            <Alert className={`${styles.bgClass} ${className}`}>
                <Icon className={`h-4 w-4 ${styles.iconClass}`} />
                <AlertTitle className="flex items-center gap-2">
                    {reason.label}
                    <Badge variant={styles.badgeVariant} className="text-xs">
                        {reason.severity.toUpperCase()}
                    </Badge>
                </AlertTitle>
                <AlertDescription className="mt-1">
                    {reason.details}
                    {reason.affectedFields && reason.affectedFields.length > 0 && (
                        <span className="block mt-1 text-xs opacity-75">
                            Betroffene Felder: {reason.affectedFields.join(', ')}
                        </span>
                    )}
                </AlertDescription>
            </Alert>
        )
    }

    // Mehrere Gründe als kompakte Liste
    return (
        <Alert className={`${styles.bgClass} ${className}`}>
            <AlertTriangle className={`h-4 w-4 ${styles.iconClass}`} />
            <AlertTitle className="flex items-center gap-2">
                {sortedReasons.length} Gründe zur Prüfung
                <Badge variant={styles.badgeVariant} className="text-xs">
                    {highestSeverity.toUpperCase()}
                </Badge>
            </AlertTitle>
            <AlertDescription className="mt-2">
                <ul className="space-y-1.5">
                    {sortedReasons.map((reason, i) => {
                        const Icon = FLAG_ICONS[reason.type]
                        const itemStyles = SEVERITY_STYLES[reason.severity]

                        return (
                            <li key={i} className="flex items-start gap-2 text-sm">
                                <Icon className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${itemStyles.iconClass}`} />
                                <span>
                                    <strong>{reason.label}:</strong> {reason.details}
                                </span>
                            </li>
                        )
                    })}
                </ul>
            </AlertDescription>
        </Alert>
    )
}

/**
 * Kompakte Version für den Header
 */
export function FlagReasonBadges({ reasons, className }: FlagReasonBannerProps) {
    if (reasons.length === 0) {
        return null
    }

    return (
        <div className={`flex flex-wrap gap-1.5 ${className}`}>
            {reasons.map((reason, i) => {
                const styles = SEVERITY_STYLES[reason.severity]

                return (
                    <Badge
                        key={i}
                        variant={styles.badgeVariant}
                        className="text-xs"
                        title={reason.details}
                    >
                        {reason.label}
                    </Badge>
                )
            })}
        </div>
    )
}
