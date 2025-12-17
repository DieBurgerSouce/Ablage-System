import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import {
    Brain,
    TrendingUp,
    RefreshCw,
    Clock,
    FileCheck,
    BarChart3,
    Lightbulb,
    AlertTriangle,
} from 'lucide-react'
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from 'recharts'
import {
    BACKEND_CONFIG,
    getBackendDisplayName,
} from '../constants/backend-config'
import {
    useLearnedWeights,
    useOverviewStats,
    useTrendData,
} from '../hooks/use-training-queries'

export function LearningInsights() {
    const [trendDays, setTrendDays] = useState<7 | 30 | 90>(30)

    const { data: learnedWeights, isLoading: isLoadingWeights, refetch: refetchWeights } = useLearnedWeights()
    const { data: overview } = useOverviewStats()
    const { data: trendData } = useTrendData({ days: trendDays })

    // Berechne den besten Backend basierend auf Gewichten
    let bestBackend: string | null = null
    let bestWeight = 0
    if (learnedWeights?.weights) {
        Object.entries(learnedWeights.weights).forEach(([backend, weight]) => {
            const weightNum = Number(weight) || 0
            if (weightNum > bestWeight) {
                bestWeight = weightNum
                bestBackend = backend
            }
        })
    }

    // Gruppiere Trend-Daten nach Datum für den Chart
    const chartData = trendData?.reduce((acc, point) => {
        const date = new Date(point.date).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
        if (!acc[date]) {
            acc[date] = { date }
        }
        if (point.backend && point.avg_cer !== undefined) {
            acc[date][`${point.backend}_cer`] = point.avg_cer * 100
        }
        return acc
    }, {} as Record<string, Record<string, string | number>>)

    const chartDataArray = chartData ? Object.values(chartData) : []

    // Generiere Insights basierend auf Daten
    const insights: { type: 'success' | 'warning' | 'info'; message: string }[] = []

    if (bestBackend && bestWeight > 0.5) {
        insights.push({
            type: 'success',
            message: `${getBackendDisplayName(bestBackend)} hat die höchste Gewichtung (${(Number(bestWeight) * 100).toFixed(0)}%)`,
        })
    }

    if (overview?.unprocessed_corrections && overview.unprocessed_corrections > 10) {
        insights.push({
            type: 'warning',
            message: `${overview.unprocessed_corrections} Korrekturen warten auf Verarbeitung`,
        })
    }

    if (learnedWeights?.confidence && learnedWeights.confidence < 0.5) {
        insights.push({
            type: 'info',
            message: 'Mehr Daten erforderlich für zuverlässige Gewichtung',
        })
    }

    if (learnedWeights?.samples_analyzed && learnedWeights.samples_analyzed < 100) {
        insights.push({
            type: 'info',
            message: `Erst ${learnedWeights.samples_analyzed} Samples analysiert`,
        })
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold flex items-center gap-2">
                        <Brain className="h-6 w-6" />
                        Self-Learning Status
                    </h2>
                    <p className="text-muted-foreground">
                        Automatische Backend-Optimierung basierend auf Korrekturen
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs bg-green-500/10 text-green-600 border-green-500/30">
                        <span className="w-1.5 h-1.5 bg-green-500 rounded-full mr-1.5 animate-pulse" />
                        Auto-Refresh
                    </Badge>
                    <Button
                        variant="outline"
                        onClick={() => refetchWeights()}
                        disabled={isLoadingWeights}
                    >
                        <RefreshCw className={`mr-2 h-4 w-4 ${isLoadingWeights ? 'animate-spin' : ''}`} />
                        Aktualisieren
                    </Button>
                </div>
            </div>

            {/* Gewichte-Karten */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {Object.entries(BACKEND_CONFIG).map(([backendId, config]) => {
                    const weight = Number(learnedWeights?.weights?.[backendId]) || 0
                    const isBest = backendId === bestBackend

                    return (
                        <Card
                            key={backendId}
                            className={isBest ? 'ring-2 ring-green-500/30 bg-green-500/5' : ''}
                        >
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm flex items-center gap-2">
                                    <div
                                        className="w-3 h-3 rounded-full"
                                        style={{ backgroundColor: config.color }}
                                    />
                                    {config.displayName}
                                    {isBest && (
                                        <Badge className="bg-green-600 text-xs ml-auto">
                                            Beste Wahl
                                        </Badge>
                                    )}
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-muted-foreground">Gewichtung</span>
                                        <span className="font-bold text-lg">
                                            {(weight * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                    <Progress
                                        value={weight * 100}
                                        className="h-2"
                                        style={{
                                            ['--progress-color' as string]: config.color,
                                        }}
                                    />
                                </div>
                            </CardContent>
                        </Card>
                    )
                })}
            </div>

            {/* Stats & Insights */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Statistiken */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm flex items-center gap-2">
                            <BarChart3 className="h-4 w-4" />
                            Lern-Statistiken
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="flex justify-between items-center">
                            <span className="text-muted-foreground text-sm">Analysierte Samples</span>
                            <span className="font-semibold">
                                {learnedWeights?.samples_analyzed?.toLocaleString('de-DE') ?? 0}
                            </span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-muted-foreground text-sm">Konfidenz</span>
                            <Badge
                                variant={
                                    (learnedWeights?.confidence ?? 0) >= 0.7
                                        ? 'default'
                                        : (learnedWeights?.confidence ?? 0) >= 0.4
                                          ? 'secondary'
                                          : 'outline'
                                }
                            >
                                {learnedWeights?.confidence !== undefined
                                    ? `${(Number(learnedWeights.confidence) * 100).toFixed(0)}%`
                                    : '-'}
                            </Badge>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-muted-foreground text-sm flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                Letzte Aktualisierung
                            </span>
                            <span className="text-sm">
                                {learnedWeights?.last_updated
                                    ? new Date(learnedWeights.last_updated).toLocaleString('de-DE')
                                    : '-'}
                            </span>
                        </div>
                    </CardContent>
                </Card>

                {/* Korrekturen */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm flex items-center gap-2">
                            <FileCheck className="h-4 w-4" />
                            Korrektur-Pipeline
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="flex justify-between items-center">
                            <span className="text-muted-foreground text-sm">24h Korrekturen</span>
                            <span className="font-semibold">
                                {overview?.recent_corrections_24h ?? 0}
                            </span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-muted-foreground text-sm">Unverarbeitet</span>
                            <Badge
                                variant={
                                    (overview?.unprocessed_corrections ?? 0) === 0
                                        ? 'default'
                                        : (overview?.unprocessed_corrections ?? 0) < 20
                                          ? 'secondary'
                                          : 'destructive'
                                }
                            >
                                {overview?.unprocessed_corrections ?? 0}
                            </Badge>
                        </div>
                        <div className="flex justify-between items-center">
                            <span className="text-muted-foreground text-sm">Verifiziert</span>
                            <span className="font-semibold">
                                {overview?.verified_samples ?? 0}
                            </span>
                        </div>
                    </CardContent>
                </Card>

                {/* Insights */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm flex items-center gap-2">
                            <Lightbulb className="h-4 w-4" />
                            Erkenntnisse
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {insights.length > 0 ? (
                            <ul className="space-y-2">
                                {insights.map((insight, i) => (
                                    <li
                                        key={i}
                                        className={`text-sm flex items-start gap-2 ${
                                            insight.type === 'success'
                                                ? 'text-green-600'
                                                : insight.type === 'warning'
                                                  ? 'text-yellow-600'
                                                  : 'text-blue-600'
                                        }`}
                                    >
                                        {insight.type === 'warning' ? (
                                            <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                                        ) : (
                                            <Lightbulb className="h-4 w-4 mt-0.5 flex-shrink-0" />
                                        )}
                                        {insight.message}
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p className="text-sm text-muted-foreground">
                                Noch keine Erkenntnisse verfügbar
                            </p>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Trend-Chart */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="flex items-center gap-2">
                                <TrendingUp className="h-5 w-5" />
                                Performance-Entwicklung
                            </CardTitle>
                            <CardDescription>
                                CER (Character Error Rate) pro Backend über Zeit
                            </CardDescription>
                        </div>
                        <div className="flex gap-2">
                            {([7, 30, 90] as const).map((days) => (
                                <Button
                                    key={days}
                                    variant={trendDays === days ? 'default' : 'outline'}
                                    size="sm"
                                    onClick={() => setTrendDays(days)}
                                >
                                    {days} Tage
                                </Button>
                            ))}
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    {chartDataArray.length > 0 ? (
                        <div className="h-[300px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={chartDataArray}>
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="date" />
                                    <YAxis domain={[0, 'auto']} />
                                    <Tooltip
                                        formatter={(value: number) => `${Number(value).toFixed(2)}%`}
                                    />
                                    <Legend />
                                    {Object.entries(BACKEND_CONFIG).map(([backendId, config]) => (
                                        <Line
                                            key={backendId}
                                            type="monotone"
                                            dataKey={`${backendId}_cer`}
                                            stroke={config.color}
                                            strokeWidth={2}
                                            dot={{ r: 3 }}
                                            name={`${config.displayName} CER`}
                                            connectNulls
                                        />
                                    ))}
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                            Keine Trend-Daten verfügbar
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Gewichtungs-Erklärung */}
            <Card className="bg-muted/30">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Wie funktioniert Self-Learning?</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground space-y-2">
                    <p>
                        Das System lernt automatisch aus Benutzer-Korrekturen und Verifikationen.
                    </p>
                    <ul className="list-disc list-inside space-y-1">
                        <li>Korrekturen werden analysiert und Fehlertypen kategorisiert</li>
                        <li>Backends mit weniger Fehlern erhalten höheres Gewicht</li>
                        <li>Umlaut-Fehler werden stärker gewichtet (kritisch für Deutsch)</li>
                        <li>Die Gewichte beeinflussen die Backend-Empfehlung für neue Dokumente</li>
                    </ul>
                </CardContent>
            </Card>
        </div>
    )
}
