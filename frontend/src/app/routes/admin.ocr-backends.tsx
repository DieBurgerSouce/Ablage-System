import { createFileRoute, Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
    ArrowRight,
    Cpu,
    Zap,
    Trophy,
    BarChart3,
    Play,
} from 'lucide-react'
import { trainingService } from '@/lib/api/services/training'
import {
    RadarChart,
    PolarGrid,
    PolarAngleAxis,
    PolarRadiusAxis,
    Radar,
    ResponsiveContainer,
    Legend,
} from 'recharts'

export const Route = createFileRoute('/admin/ocr-backends')({
    component: OCRBackendsPage,
})

// Backend-Konfiguration mit deutschen Display-Namen
const BACKEND_CONFIG: Record<string, {
    displayName: string
    vramGB: number
    requiresGPU: boolean
    color: string
    description: string
}> = {
    'deepseek-janus-pro': {
        displayName: 'DeepSeek-Janus-Pro',
        vramGB: 12,
        requiresGPU: true,
        color: '#8884d8',
        description: 'Beste Umlaut-Genauigkeit, Fraktur, komplexe Layouts',
    },
    'got-ocr-2.0': {
        displayName: 'GOT-OCR 2.0',
        vramGB: 10,
        requiresGPU: true,
        color: '#82ca9d',
        description: 'Tabellen, Formeln, schnell',
    },
    'surya-gpu': {
        displayName: 'Surya GPU',
        vramGB: 4,
        requiresGPU: true,
        color: '#ffc658',
        description: 'Schnelle GPU-Variante',
    },
    'surya': {
        displayName: 'Surya (CPU)',
        vramGB: 0,
        requiresGPU: false,
        color: '#ff8042',
        description: 'CPU-Fallback, Layout-Analyse',
    },
}

function OCRBackendsPage() {
    const { data: comparison } = useQuery({
        queryKey: ['training', 'comparison'],
        queryFn: () => trainingService.getBackendComparison(),
    })

    const { data: learnedWeights } = useQuery({
        queryKey: ['training', 'learned-weights'],
        queryFn: () => trainingService.getLearnedWeights(false),
    })

    useQuery({
        queryKey: ['training', 'backends'],
        queryFn: () => trainingService.getAvailableBackends(),
    })

    // Radar Chart Daten vorbereiten
    const radarData = comparison ? [
        {
            metric: 'Genauigkeit',
            ...Object.fromEntries(
                Object.entries(comparison.backends).map(([name, data]) => [
                    name,
                    data.avg_cer !== undefined ? Math.max(0, (1 - data.avg_cer) * 100) : 0,
                ])
            ),
        },
        {
            metric: 'Umlaute',
            ...Object.fromEntries(
                Object.entries(comparison.backends).map(([name, data]) => [
                    name,
                    data.avg_umlaut_accuracy !== undefined ? data.avg_umlaut_accuracy * 100 : 0,
                ])
            ),
        },
        {
            metric: 'Geschwindigkeit',
            ...Object.fromEntries(
                Object.entries(comparison.backends).map(([name, data]) => [
                    name,
                    data.avg_processing_time_ms !== undefined
                        ? Math.max(0, 100 - (data.avg_processing_time_ms / 50))
                        : 0,
                ])
            ),
        },
        {
            metric: 'Konsistenz',
            ...Object.fromEntries(
                Object.entries(comparison.backends).map(([name, data]) => [
                    name,
                    data.p90_cer !== undefined && data.avg_cer !== undefined
                        ? Math.max(0, 100 - ((data.p90_cer - data.avg_cer) * 500))
                        : 50,
                ])
            ),
        },
    ] : []

    return (
        <div className="max-w-7xl mx-auto p-8 space-y-8">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight font-display">
                        OCR Backends
                    </h1>
                    <p className="text-muted-foreground mt-2">
                        Vergleichen Sie die Performance der 4 OCR-Engines und starten Sie Benchmarks.
                    </p>
                </div>
                <Button>
                    <Play className="mr-2 h-4 w-4" />
                    Benchmark starten
                </Button>
            </div>

            {/* Backend Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {Object.entries(BACKEND_CONFIG).map(([backendId, config]) => {
                    const stats = comparison?.backends[backendId]
                    const weight = learnedWeights?.weights?.[backendId]
                    const isBestBackend = comparison?.best_backend === backendId

                    return (
                        <Link
                            key={backendId}
                            to="/admin/ocr-backends/$backend"
                            params={{ backend: backendId }}
                            className="block"
                        >
                            <Card
                                className={`hover:border-primary/50 transition-colors cursor-pointer ${
                                    isBestBackend ? 'ring-2 ring-green-500/30 bg-green-500/5' : ''
                                }`}
                            >
                                <CardHeader className="pb-2">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            <div
                                                className="w-3 h-3 rounded-full"
                                                style={{ backgroundColor: config.color }}
                                            />
                                            <CardTitle className="text-lg">
                                                {config.displayName}
                                            </CardTitle>
                                            {isBestBackend && (
                                                <Badge variant="default" className="bg-green-600">
                                                    <Trophy className="mr-1 h-3 w-3" />
                                                    Bester
                                                </Badge>
                                            )}
                                        </div>
                                        <ArrowRight className="h-5 w-5 text-muted-foreground" />
                                    </div>
                                    <CardDescription>{config.description}</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    {/* VRAM & GPU Info */}
                                    <div className="flex items-center gap-4">
                                        <div className="flex items-center gap-2">
                                            {config.requiresGPU ? (
                                                <Zap className="h-4 w-4 text-yellow-500" />
                                            ) : (
                                                <Cpu className="h-4 w-4 text-blue-500" />
                                            )}
                                            <span className="text-sm text-muted-foreground">
                                                {config.requiresGPU ? 'GPU' : 'CPU'}
                                            </span>
                                        </div>
                                        <div className="flex-1">
                                            <Progress
                                                value={(config.vramGB / 16) * 100}
                                                className="h-2"
                                            />
                                        </div>
                                        <span className="text-sm font-medium">
                                            {config.vramGB} GB VRAM
                                        </span>
                                    </div>

                                    {/* Metriken */}
                                    {stats ? (
                                        <div className="grid grid-cols-3 gap-4 pt-2 border-t">
                                            <div>
                                                <p className="text-xs text-muted-foreground">CER</p>
                                                <p
                                                    className={`text-lg font-semibold ${
                                                        (stats.avg_cer ?? 0) < 0.05
                                                            ? 'text-green-600'
                                                            : (stats.avg_cer ?? 0) < 0.1
                                                              ? 'text-yellow-600'
                                                              : 'text-red-600'
                                                    }`}
                                                >
                                                    {stats.avg_cer !== undefined
                                                        ? `${(stats.avg_cer * 100).toFixed(1)}%`
                                                        : '-'}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-muted-foreground">Umlaut</p>
                                                <p
                                                    className={`text-lg font-semibold ${
                                                        (stats.avg_umlaut_accuracy ?? 0) >= 0.99
                                                            ? 'text-green-600'
                                                            : (stats.avg_umlaut_accuracy ?? 0) >= 0.95
                                                              ? 'text-yellow-600'
                                                              : 'text-red-600'
                                                    }`}
                                                >
                                                    {stats.avg_umlaut_accuracy !== undefined
                                                        ? `${(stats.avg_umlaut_accuracy * 100).toFixed(0)}%`
                                                        : '-'}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-muted-foreground">Samples</p>
                                                <p className="text-lg font-semibold">
                                                    {stats.samples_processed?.toLocaleString('de-DE') ?? 0}
                                                </p>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="py-4 text-center text-muted-foreground text-sm">
                                            Keine Benchmark-Daten
                                        </div>
                                    )}

                                    {/* Gewichtung */}
                                    {weight !== undefined && (
                                        <div className="flex items-center justify-between pt-2 border-t">
                                            <span className="text-sm text-muted-foreground">
                                                Gelernte Gewichtung
                                            </span>
                                            <Badge variant="outline">
                                                {(weight * 100).toFixed(0)}%
                                            </Badge>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </Link>
                    )
                })}
            </div>

            {/* Radar Chart Vergleich */}
            {comparison && Object.keys(comparison.backends).length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <BarChart3 className="h-5 w-5" />
                            Multidimensionaler Vergleich
                        </CardTitle>
                        <CardDescription>
                            Vergleich aller Backends nach Genauigkeit, Umlaut-Erkennung,
                            Geschwindigkeit und Konsistenz
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[400px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <RadarChart data={radarData}>
                                    <PolarGrid />
                                    <PolarAngleAxis dataKey="metric" />
                                    <PolarRadiusAxis angle={30} domain={[0, 100]} />
                                    {Object.keys(BACKEND_CONFIG).map((backendId) => (
                                        <Radar
                                            key={backendId}
                                            name={BACKEND_CONFIG[backendId].displayName}
                                            dataKey={backendId}
                                            stroke={BACKEND_CONFIG[backendId].color}
                                            fill={BACKEND_CONFIG[backendId].color}
                                            fillOpacity={0.2}
                                        />
                                    ))}
                                    <Legend />
                                </RadarChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Quick Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            Insgesamt Samples
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-2xl font-bold">
                            {comparison?.sample_count?.toLocaleString('de-DE') ?? 0}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            Bester Backend
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-2xl font-bold">
                            {comparison?.best_backend
                                ? BACKEND_CONFIG[comparison.best_backend]?.displayName ?? comparison.best_backend
                                : '-'}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            Letzte Gewichtung
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-2xl font-bold">
                            {learnedWeights?.last_updated
                                ? new Date(learnedWeights.last_updated).toLocaleDateString('de-DE')
                                : '-'}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            Konfidenz
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-2xl font-bold">
                            {learnedWeights?.confidence !== undefined
                                ? `${(learnedWeights.confidence * 100).toFixed(0)}%`
                                : '-'}
                        </p>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
