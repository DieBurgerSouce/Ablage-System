/**
 * ConfidenceLegend - Farbskala-Legende für Confidence-Level
 *
 * Zeigt horizontale Leiste mit Confidence-Gradienten
 * und Wort-Zaehler pro Kategorie.
 */

import { useMemo } from 'react'
import { Badge } from '@/components/ui/badge'
import type { WordConfidence } from '../api/confidence-api'
import { getConfidenceLevel } from '../api/confidence-api'

interface ConfidenceLegendProps {
    words: WordConfidence[]
    className?: string
}

interface BucketInfo {
    label: string
    range: string
    _colorClass: string
    bgClass: string
    count: number
}

export function ConfidenceLegend({ words, className }: ConfidenceLegendProps) {
    const buckets = useMemo((): BucketInfo[] => {
        let critical = 0
        let low = 0
        let uncertain = 0
        let high = 0

        for (const word of words) {
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

        return [
            {
                label: 'Kritisch',
                range: '<60%',
                _colorClass: 'bg-red-500',
                bgClass: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300',
                count: critical,
            },
            {
                label: 'Niedrig',
                range: '60-80%',
                _colorClass: 'bg-orange-500',
                bgClass: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300',
                count: low,
            },
            {
                label: 'Unsicher',
                range: '80-95%',
                _colorClass: 'bg-yellow-500',
                bgClass: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300',
                count: uncertain,
            },
            {
                label: 'Sicher',
                range: '>95%',
                _colorClass: 'bg-green-500',
                bgClass: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
                count: high,
            },
        ]
    }, [words])

    return (
        <div className={className}>
            {/* Gradient Bar */}
            <div className="flex h-2 rounded-full overflow-hidden">
                <div className="bg-red-500 flex-1" />
                <div className="bg-orange-500 flex-1" />
                <div className="bg-yellow-500 flex-1" />
                <div className="bg-green-500 flex-1" />
            </div>

            {/* Labels */}
            <div className="flex justify-between mt-1.5 gap-1">
                {buckets.map((bucket) => (
                    <div
                        key={bucket.label}
                        className="flex flex-col items-center text-center flex-1 min-w-0"
                    >
                        <span className="text-[10px] text-muted-foreground truncate">
                            {bucket.label}
                        </span>
                        <span className="text-[10px] text-muted-foreground/70">
                            {bucket.range}
                        </span>
                        {bucket.count > 0 && (
                            <Badge variant="secondary" className={`text-[10px] h-auto py-0.5 px-1.5 mt-0.5 ${bucket.bgClass}`}>
                                {bucket.count}
                            </Badge>
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}
