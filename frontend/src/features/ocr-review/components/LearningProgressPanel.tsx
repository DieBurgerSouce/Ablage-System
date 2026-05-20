/**
 * Learning Progress Panel
 * Zeigt den Self-Learning Fortschritt und gelernte Backend-Gewichte
 */

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import {
    Brain,
    TrendingUp,
    TrendingDown,
    Minus,
    AlertCircle,
    RefreshCw,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { LearnedWeights } from '../types'
import { BACKEND_CONFIG } from '@/features/ocr-training/constants/backend-config'

interface LearningProgressPanelProps {
    weights: LearnedWeights | undefined
    isLoading: boolean
    onRefresh?: () => void
}

export function LearningProgressPanel({
    weights,
    isLoading,
    onRefresh,
}: LearningProgressPanelProps) {
    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Brain className="h-5 w-5" />
                        Self-Learning Status
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-8 w-full" />
                    <Skeleton className="h-8 w-full" />
                    <Skeleton className="h-8 w-full" />
                </CardContent>
            </Card>
        )
    }

    const hasData = weights && weights.samples_analyzed > 0
    const confidencePercent = Number(weights?.confidence || 0) * 100

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center justify-between">
                    <span className="flex items-center gap-2">
                        <Brain className="h-5 w-5" />
                        Self-Learning Status
                    </span>
                    {onRefresh && (
                        <Button variant="ghost" size="sm" onClick={onRefresh}>
                            <RefreshCw className="h-4 w-4" />
                        </Button>
                    )}
                </CardTitle>
                <CardDescription>
                    {hasData
                        ? `Basierend auf ${weights.samples_analyzed} Korrekturen`
                        : 'Noch keine Korrekturen eingereicht'}
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {!hasData ? (
                    <div className="flex flex-col items-center justify-center py-6 text-center">
                        <AlertCircle className="h-12 w-12 text-muted-foreground mb-3" />
                        <p className="text-sm text-muted-foreground">
                            Starte den Review-Prozess und reiche Korrekturen ein,
                            <br />
                            um das Self-Learning zu aktivieren.
                        </p>
                    </div>
                ) : (
                    <>
                        {/* Konfidenz-Anzeige */}
                        <div className="space-y-1">
                            <div className="flex items-center justify-between text-sm">
                                <span>Lern-Konfidenz</span>
                                <span className="font-medium">{confidencePercent.toFixed(0)}%</span>
                            </div>
                            <Progress value={confidencePercent} />
                            <p className="text-xs text-muted-foreground">
                                {confidencePercent < 50
                                    ? 'Mehr Korrekturen nötig für zuverlässige Gewichtung'
                                    : confidencePercent < 80
                                        ? 'Gute Datenbasis, Gewichte werden präziser'
                                        : 'Hohe Konfidenz in der Backend-Gewichtung'}
                            </p>
                        </div>

                        {/* Backend Gewichte */}
                        <div className="space-y-3">
                            <h4 className="text-sm font-medium">Backend-Gewichte</h4>
                            {Object.entries(weights.weights || {})
                                .sort((a, b) => Number(b[1]) - Number(a[1]))
                                .map(([backend, weight]) => {
                                    const weightNum = Number(weight) || 0
                                    const config = BACKEND_CONFIG[backend as keyof typeof BACKEND_CONFIG]
                                    const displayName = config?.displayName || backend
                                    const color = config?.color || '#666'

                                    // Gewicht relativ zu 1.0 (Baseline)
                                    const deviation = weightNum - 1.0
                                    const percent = Math.min(100, Math.max(0, weightNum * 50))

                                    return (
                                        <div key={backend} className="space-y-1">
                                            <div className="flex items-center justify-between text-sm">
                                                <div className="flex items-center gap-2">
                                                    <div
                                                        className="w-3 h-3 rounded-full"
                                                        style={{ backgroundColor: color }}
                                                    />
                                                    <span>{displayName}</span>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <span className="font-mono font-medium">
                                                        {weightNum.toFixed(2)}
                                                    </span>
                                                    <WeightTrend deviation={deviation} />
                                                </div>
                                            </div>
                                            <Progress
                                                value={percent}
                                                className="h-2"
                                                style={{
                                                    // @ts-expect-error CSS custom property
                                                    '--progress-color': color,
                                                }}
                                            />
                                        </div>
                                    )
                                })}
                        </div>

                        {/* Error Patterns */}
                        {weights.error_patterns && Object.keys(weights.error_patterns).length > 0 && (
                            <div className="space-y-2 pt-2 border-t">
                                <h4 className="text-sm font-medium">Häufigste Fehlertypen</h4>
                                <div className="flex flex-wrap gap-2">
                                    {Object.entries(weights.error_patterns)
                                        .flatMap(([backend, pattern]) =>
                                            Object.entries(pattern.correction_types || {}).map(
                                                ([type, count]) => ({
                                                    backend,
                                                    type,
                                                    count: count as number,
                                                })
                                            )
                                        )
                                        .sort((a, b) => b.count - a.count)
                                        .slice(0, 5)
                                        .map(({ type, count }, i) => (
                                            <Badge key={i} variant="outline" className="text-xs">
                                                {formatCorrectionType(type)}: {count}
                                            </Badge>
                                        ))}
                                </div>
                            </div>
                        )}

                        {/* Letzte Aktualisierung */}
                        {weights.last_updated && (
                            <p className="text-xs text-muted-foreground pt-2 border-t">
                                Zuletzt aktualisiert:{' '}
                                {new Date(weights.last_updated).toLocaleString('de-DE')}
                            </p>
                        )}
                    </>
                )}
            </CardContent>
        </Card>
    )
}

function WeightTrend({ deviation }: { deviation: number }) {
    const dev = Number(deviation) || 0
    if (Math.abs(dev) < 0.02) {
        return <Minus className="h-4 w-4 text-muted-foreground" />
    }
    if (dev > 0) {
        return (
            <span className="flex items-center text-green-600">
                <TrendingUp className="h-4 w-4" />
                <span className="text-xs ml-0.5">+{(dev * 100).toFixed(0)}%</span>
            </span>
        )
    }
    return (
        <span className="flex items-center text-red-600">
            <TrendingDown className="h-4 w-4" />
            <span className="text-xs ml-0.5">{(dev * 100).toFixed(0)}%</span>
        </span>
    )
}

function formatCorrectionType(type: string): string {
    const map: Record<string, string> = {
        UMLAUT: 'Umlaut',
        DATE: 'Datum',
        AMOUNT: 'Betrag',
        NUMBER: 'Nummer',
        NAME: 'Name',
        IBAN: 'IBAN',
        VAT_ID: 'USt-Id',
        GENERAL: 'Allgemein',
    }
    return map[type] || type
}
