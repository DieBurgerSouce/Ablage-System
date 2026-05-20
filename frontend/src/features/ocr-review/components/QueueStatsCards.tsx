/**
 * Queue Stats Cards Komponente
 * Zeigt Statistiken zur Verification Queue
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
    Clock,
    AlertCircle,
    CheckCircle2,
    Eye,
    TrendingUp,
    FileText,
} from 'lucide-react'
import type { QueueStats } from '../types'

interface QueueStatsCardsProps {
    stats: QueueStats
    sessionStats?: {
        reviewed_today: number
        corrections_today: number
    }
    isLoading?: boolean
}

export function QueueStatsCards({ stats, sessionStats, isLoading }: QueueStatsCardsProps) {
    if (isLoading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {[1, 2, 3, 4].map((i) => (
                    <Card key={i} className="animate-pulse">
                        <CardHeader className="pb-2">
                            <div className="h-4 bg-muted rounded w-24" />
                        </CardHeader>
                        <CardContent>
                            <div className="h-8 bg-muted rounded w-16" />
                        </CardContent>
                    </Card>
                ))}
            </div>
        )
    }

    const criticalCount = stats.pending_by_priority?.CRITICAL || 0
    const highCount = stats.pending_by_priority?.HIGH || 0
    const urgentCount = criticalCount + highCount

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Ausstehend */}
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Ausstehend</CardTitle>
                    <Clock className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">{stats.total_pending.toLocaleString('de-DE')}</div>
                    <div className="flex items-center gap-2 mt-1">
                        {urgentCount > 0 && (
                            <Badge variant="destructive" className="text-xs">
                                {urgentCount} dringend
                            </Badge>
                        )}
                        {stats.oldest_item_days > 7 && (
                            <Badge variant="outline" className="text-xs">
                                Ältestes: {stats.oldest_item_days}d
                            </Badge>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* Stichproben */}
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Stichproben</CardTitle>
                    <Eye className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">{stats.spot_checks_pending}</div>
                    <p className="text-xs text-muted-foreground mt-1">
                        10% der auto-akzeptierten Samples
                    </p>
                </CardContent>
            </Card>

            {/* Coverage-Lücken */}
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Coverage-Lücken</CardTitle>
                    <AlertCircle className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">
                        {stats.coverage_gaps?.length || 0}
                    </div>
                    {stats.coverage_gaps && stats.coverage_gaps.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                            {stats.coverage_gaps.slice(0, 2).map((gap) => (
                                <Badge key={gap.document_type} variant="secondary" className="text-xs">
                                    {gap.document_type}: {Math.round(gap.current_coverage * 100)}%
                                </Badge>
                            ))}
                            {stats.coverage_gaps.length > 2 && (
                                <Badge variant="outline" className="text-xs">
                                    +{stats.coverage_gaps.length - 2}
                                </Badge>
                            )}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Heute reviewed */}
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Heute</CardTitle>
                    <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">
                        {sessionStats?.reviewed_today || 0}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                        <Badge variant="outline" className="text-xs">
                            {sessionStats?.corrections_today || 0} Korrekturen
                        </Badge>
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}

interface CoverageByTypeProps {
    stats: QueueStats
}

export function CoverageByType({ stats }: CoverageByTypeProps) {
    const types = Object.entries(stats.pending_by_type || {}).sort((a, b) => b[1] - a[1])

    if (types.length === 0) return null

    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <FileText className="h-4 w-4" />
                    Nach Dokumenttyp
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
                {types.slice(0, 6).map(([type, count]) => {
                    const gap = stats.coverage_gaps?.find((g) => g.document_type === type)
                    const coverage = gap ? gap.current_coverage * 100 : 100
                    const isGap = gap && gap.current_coverage < gap.target_coverage

                    return (
                        <div key={type} className="space-y-1">
                            <div className="flex items-center justify-between text-sm">
                                <span className="font-medium capitalize">{type}</span>
                                <div className="flex items-center gap-2">
                                    <span className="text-muted-foreground">{count}</span>
                                    {isGap && (
                                        <Badge variant="destructive" className="text-xs">
                                            {Math.round(coverage)}%
                                        </Badge>
                                    )}
                                </div>
                            </div>
                            <Progress
                                value={coverage}
                                className={isGap ? 'bg-destructive/20' : undefined}
                            />
                        </div>
                    )
                })}
            </CardContent>
        </Card>
    )
}

interface PriorityBreakdownProps {
    stats: QueueStats
}

export function PriorityBreakdown({ stats }: PriorityBreakdownProps) {
    const priorities = [
        { key: 'critical', label: 'Kritisch', color: 'bg-red-500' },
        { key: 'high', label: 'Hoch', color: 'bg-orange-500' },
        { key: 'medium', label: 'Mittel', color: 'bg-yellow-500' },
        { key: 'low', label: 'Niedrig', color: 'bg-green-500' },
    ]

    const total = stats.total_pending || 1

    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <TrendingUp className="h-4 w-4" />
                    Nach Priorität
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
                {priorities.map(({ key, label, color }) => {
                    const count = Number(stats.pending_by_priority?.[key]) || 0
                    const percent = Number.isFinite(count / total) ? (count / total) * 100 : 0

                    return (
                        <div key={key} className="flex items-center gap-3">
                            <div className={`w-3 h-3 rounded-full ${color}`} />
                            <span className="text-sm flex-1">{label}</span>
                            <span className="text-sm font-medium">{count}</span>
                            <span className="text-xs text-muted-foreground w-12 text-right">
                                {percent.toFixed(0)}%
                            </span>
                        </div>
                    )
                })}
            </CardContent>
        </Card>
    )
}
