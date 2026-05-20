/**
 * ConfidenceStats - Schnelle Statistik-Anzeige für Confidence-Daten
 *
 * Zeigt Gesamt-Confidence, Wort-Zaehler und Backend-Info.
 */

import { useMemo } from 'react'
import { Badge } from '@/components/ui/badge'
import type { PageConfidence } from '../api/confidence-api'
import { getConfidenceLevel } from '../api/confidence-api'

interface ConfidenceStatsProps {
    overallConfidence: number
    pages: PageConfidence[]
    backend: string
    className?: string
}

export function ConfidenceStats({
    overallConfidence,
    pages,
    backend,
    className,
}: ConfidenceStatsProps) {
    const stats = useMemo(() => {
        let totalWords = 0
        let critical = 0
        let low = 0
        let uncertain = 0
        let high = 0

        for (const page of pages) {
            for (const word of page.words) {
                totalWords++
                const level = getConfidenceLevel(word.confidence)
                switch (level) {
                    case 'critical':
                        critical++
                        break
                    case 'low':
                        low++
                        break
                    case 'uncertain':
                        uncertain++
                        break
                    case 'high':
                        high++
                        break
                }
            }
        }

        return { totalWords, critical, low, uncertain, high }
    }, [pages])

    const confidencePercent = Math.round(overallConfidence * 100)
    const confidenceColor =
        confidencePercent >= 95
            ? 'text-green-600 dark:text-green-400'
            : confidencePercent >= 80
              ? 'text-yellow-600 dark:text-yellow-400'
              : confidencePercent >= 60
                ? 'text-orange-600 dark:text-orange-400'
                : 'text-red-600 dark:text-red-400'

    return (
        <div className={className}>
            <div className="flex items-center gap-4">
                {/* Overall Confidence */}
                <div className="flex items-baseline gap-1">
                    <span className={`text-2xl font-bold tabular-nums ${confidenceColor}`}>
                        {confidencePercent}%
                    </span>
                    <span className="text-xs text-muted-foreground">Gesamt</span>
                </div>

                {/* Badges */}
                <div className="flex items-center gap-1.5 flex-wrap">
                    <Badge variant="outline" className="text-xs">
                        {backend}
                    </Badge>
                    {stats.totalWords > 0 && (
                        <Badge variant="secondary" className="text-xs">
                            {stats.totalWords} Wörter
                        </Badge>
                    )}
                </div>
            </div>

            {/* Bucket Bars */}
            {stats.totalWords > 0 && (
                <div className="flex items-center gap-1 mt-2">
                    {stats.high > 0 && (
                        <div
                            className="h-1.5 bg-green-500 rounded-full"
                            style={{
                                width: `${(stats.high / stats.totalWords) * 100}%`,
                                minWidth: '2px',
                            }}
                            title={`${stats.high} sicher (>95%)`}
                        />
                    )}
                    {stats.uncertain > 0 && (
                        <div
                            className="h-1.5 bg-yellow-500 rounded-full"
                            style={{
                                width: `${(stats.uncertain / stats.totalWords) * 100}%`,
                                minWidth: '2px',
                            }}
                            title={`${stats.uncertain} unsicher (80-95%)`}
                        />
                    )}
                    {stats.low > 0 && (
                        <div
                            className="h-1.5 bg-orange-500 rounded-full"
                            style={{
                                width: `${(stats.low / stats.totalWords) * 100}%`,
                                minWidth: '2px',
                            }}
                            title={`${stats.low} niedrig (60-80%)`}
                        />
                    )}
                    {stats.critical > 0 && (
                        <div
                            className="h-1.5 bg-red-500 rounded-full"
                            style={{
                                width: `${(stats.critical / stats.totalWords) * 100}%`,
                                minWidth: '2px',
                            }}
                            title={`${stats.critical} kritisch (<60%)`}
                        />
                    )}
                </div>
            )}
        </div>
    )
}
