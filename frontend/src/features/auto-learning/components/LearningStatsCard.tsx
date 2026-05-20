/**
 * LearningStatsCard - Kompakte Statistik-Karte fuer das Admin-Dashboard
 *
 * Zeigt KI-Genauigkeit, Korrekturen, automatisch Verarbeitete
 * und Durchschnittskonfidenz als kompakte Metriken.
 */

import { TrendingUp, TrendingDown, Brain, CheckCircle, AlertTriangle, BarChart3 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useLearningStats } from '../hooks/use-auto-learning'

// ==================== Helpers ====================

interface AggregatedMetrics {
    weightedAccuracy: number
    totalCorrected: number
    totalAutoApplied: number
    weightedConfidence: number
    totalDecisions: number
}

function aggregateStats(stats: { accuracyRate: number; corrected: number; autoApplied: number; avgConfidence: number; totalDecisions: number }[]): AggregatedMetrics {
    if (stats.length === 0) {
        return {
            weightedAccuracy: 0,
            totalCorrected: 0,
            totalAutoApplied: 0,
            weightedConfidence: 0,
            totalDecisions: 0,
        }
    }

    const totalDecisions = stats.reduce((sum, s) => sum + s.totalDecisions, 0)
    const totalCorrected = stats.reduce((sum, s) => sum + s.corrected, 0)
    const totalAutoApplied = stats.reduce((sum, s) => sum + s.autoApplied, 0)

    // Gewichteter Durchschnitt basierend auf Anzahl Entscheidungen
    const weightedAccuracy =
        totalDecisions > 0
            ? stats.reduce((sum, s) => sum + s.accuracyRate * s.totalDecisions, 0) / totalDecisions
            : 0

    const weightedConfidence =
        totalDecisions > 0
            ? stats.reduce((sum, s) => sum + s.avgConfidence * s.totalDecisions, 0) / totalDecisions
            : 0

    return {
        weightedAccuracy,
        totalCorrected,
        totalAutoApplied,
        weightedConfidence,
        totalDecisions,
    }
}

// ==================== Metric Item ====================

interface MetricItemProps {
    icon: React.ReactNode
    label: string
    value: string
    subtext?: string
    trend?: 'up' | 'down' | 'neutral'
}

function MetricItem({ icon, label, value, subtext, trend }: MetricItemProps) {
    return (
        <div className="flex items-center gap-3">
            <div className="flex-shrink-0 rounded-md bg-muted p-2">
                {icon}
            </div>
            <div className="flex-1 min-w-0">
                <p className="text-xs text-muted-foreground truncate">{label}</p>
                <div className="flex items-center gap-1.5">
                    <span className="text-lg font-bold leading-none">{value}</span>
                    {trend === 'up' && (
                        <TrendingUp className="h-3.5 w-3.5 text-green-500" />
                    )}
                    {trend === 'down' && (
                        <TrendingDown className="h-3.5 w-3.5 text-red-500" />
                    )}
                </div>
                {subtext && (
                    <p className="text-xs text-muted-foreground mt-0.5">{subtext}</p>
                )}
            </div>
        </div>
    )
}

// ==================== Loading Skeleton ====================

function StatsSkeleton() {
    return (
        <div className="grid grid-cols-2 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3">
                    <Skeleton className="h-9 w-9 rounded-md flex-shrink-0" />
                    <div className="space-y-1.5 flex-1">
                        <Skeleton className="h-3 w-16" />
                        <Skeleton className="h-5 w-12" />
                    </div>
                </div>
            ))}
        </div>
    )
}

// ==================== Main Component ====================

interface LearningStatsCardProps {
    days?: number
    className?: string
}

export function LearningStatsCard({ days = 30, className }: LearningStatsCardProps) {
    const { data: stats, isLoading } = useLearningStats(days)

    const metrics = stats ? aggregateStats(stats) : null

    return (
        <Card className={cn('', className)}>
            <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                    <Brain className="h-4 w-4" />
                    KI-Lernfortschritt
                </CardTitle>
            </CardHeader>
            <CardContent>
                {isLoading && <StatsSkeleton />}

                {!isLoading && metrics && (
                    <div className="grid grid-cols-2 gap-4">
                        <MetricItem
                            icon={<BarChart3 className="h-4 w-4 text-muted-foreground" />}
                            label="KI-Genauigkeit"
                            value={`${Math.round(metrics.weightedAccuracy * 100)}%`}
                            trend={metrics.weightedAccuracy >= 0.85 ? 'up' : 'down'}
                        />
                        <MetricItem
                            icon={<AlertTriangle className="h-4 w-4 text-muted-foreground" />}
                            label="Korrekturen"
                            value={String(metrics.totalCorrected)}
                            subtext={`von ${metrics.totalDecisions} gesamt`}
                        />
                        <MetricItem
                            icon={<CheckCircle className="h-4 w-4 text-muted-foreground" />}
                            label="Automatisch verarbeitet"
                            value={String(metrics.totalAutoApplied)}
                            subtext={
                                metrics.totalDecisions > 0
                                    ? `${Math.round(
                                          (metrics.totalAutoApplied / metrics.totalDecisions) * 100
                                      )}% aller Entscheidungen`
                                    : undefined
                            }
                        />
                        <MetricItem
                            icon={<Brain className="h-4 w-4 text-muted-foreground" />}
                            label="Durchschn. Konfidenz"
                            value={`${Math.round(metrics.weightedConfidence * 100)}%`}
                            trend={metrics.weightedConfidence >= 0.8 ? 'up' : 'neutral'}
                        />
                    </div>
                )}

                {!isLoading && !metrics && (
                    <p className="text-sm text-muted-foreground text-center py-4">
                        Keine Statistiken verfuegbar
                    </p>
                )}
            </CardContent>
        </Card>
    )
}
