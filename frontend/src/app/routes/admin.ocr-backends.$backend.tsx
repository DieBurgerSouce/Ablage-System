import { createFileRoute, Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import {
    ArrowLeft,
    Cpu,
    Zap,
    Trophy,
    Play,
    TrendingUp,
    FileText,
    AlertCircle,
    CheckCircle2,
    Clock,
} from 'lucide-react'
import { trainingService } from '@/lib/api/services/training'
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
import { useState } from 'react'

export const Route = createFileRoute('/admin/ocr-backends/$backend')({
    component: BackendDetailPage,
})

// Backend-Konfiguration
const BACKEND_CONFIG: Record<string, {
    displayName: string
    vramGB: number
    requiresGPU: boolean
    color: string
    description: string
    strengths: string[]
    weaknesses: string[]
}> = {
    'deepseek-janus-pro': {
        displayName: 'DeepSeek-Janus-Pro',
        vramGB: 12,
        requiresGPU: true,
        color: '#8884d8',
        description: 'Multimodales Vision-Language-Modell mit bester Umlaut-Genauigkeit',
        strengths: ['Umlaute (ae, oe, ue, ss)', 'Frakturschrift', 'Komplexe Layouts', 'Deutsche Texte'],
        weaknesses: ['Hoher VRAM-Bedarf', 'Langsamer als GOT-OCR'],
    },
    'got-ocr-2.0': {
        displayName: 'GOT-OCR 2.0',
        vramGB: 10,
        requiresGPU: true,
        color: '#82ca9d',
        description: '600M Parameter Transformer-basiertes OCR',
        strengths: ['Tabellen', 'Formeln', 'Schnelle Verarbeitung', 'Strukturierte Dokumente'],
        weaknesses: ['Umlaut-Erkennung', 'Handschrift'],
    },
    'surya-gpu': {
        displayName: 'Surya GPU',
        vramGB: 4,
        requiresGPU: true,
        color: '#ffc658',
        description: 'GPU-beschleunigte Variante von Surya',
        strengths: ['Niedriger VRAM', 'Layout-Analyse', 'Schnell'],
        weaknesses: ['Weniger genau als DeepSeek', 'Keine Fraktur'],
    },
    'surya': {
        displayName: 'Surya (CPU)',
        vramGB: 0,
        requiresGPU: false,
        color: '#ff8042',
        description: 'CPU-Fallback mit Docling-Integration',
        strengths: ['Kein GPU erforderlich', 'Stabile Performance', 'Layout-Analyse'],
        weaknesses: ['Langsam', 'Geringere Genauigkeit'],
    },
}

function BackendDetailPage() {
    const { backend } = Route.useParams()
    const [trendDays, setTrendDays] = useState<7 | 30 | 90>(30)

    const config = BACKEND_CONFIG[backend] ?? {
        displayName: backend,
        vramGB: 0,
        requiresGPU: false,
        color: '#666',
        description: 'Unbekanntes Backend',
        strengths: [],
        weaknesses: [],
    }

    const { data: comparison } = useQuery({
        queryKey: ['training', 'comparison'],
        queryFn: () => trainingService.getBackendComparison(),
    })

    const { data: learnedWeights } = useQuery({
        queryKey: ['training', 'learned-weights'],
        queryFn: () => trainingService.getLearnedWeights(false),
    })

    const { data: trendData } = useQuery({
        queryKey: ['training', 'trends', backend, trendDays],
        queryFn: () => trainingService.getTrendData({
            days: trendDays,
            backend,
        }),
    })

    const { data: samplesData } = useQuery({
        queryKey: ['training', 'samples', backend],
        queryFn: () => trainingService.listSamples({ limit: 20 }),
    })

    const stats = comparison?.backends[backend]
    const weight = learnedWeights?.weights?.[backend]
    const isBestBackend = comparison?.best_backend === backend

    // Trend-Daten für Chart vorbereiten
    const chartData = trendData?.map((point) => ({
        date: new Date(point.date).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }),
        CER: point.avg_cer !== undefined ? point.avg_cer * 100 : null,
        WER: point.avg_wer !== undefined ? point.avg_wer * 100 : null,
        Umlaut: point.avg_umlaut_accuracy !== undefined ? point.avg_umlaut_accuracy * 100 : null,
    })) ?? []

    return (
        <div className="max-w-7xl mx-auto p-8 space-y-8">
            {/* Header */}
            <div className="flex items-center gap-4">
                <Link to="/admin/ocr-backends">
                    <Button variant="ghost" size="icon">
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                </Link>
                <div className="flex-1">
                    <div className="flex items-center gap-3">
                        <div
                            className="w-4 h-4 rounded-full"
                            style={{ backgroundColor: config.color }}
                        />
                        <h1 className="text-3xl font-bold tracking-tight font-display">
                            {config.displayName}
                        </h1>
                        {isBestBackend && (
                            <Badge variant="default" className="bg-green-600">
                                <Trophy className="mr-1 h-3 w-3" />
                                Bester Backend
                            </Badge>
                        )}
                    </div>
                    <p className="text-muted-foreground mt-1">{config.description}</p>
                </div>
                <Button>
                    <Play className="mr-2 h-4 w-4" />
                    Benchmark starten
                </Button>
            </div>

            {/* Quick Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            CER (Character Error Rate)
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p
                            className={`text-3xl font-bold ${
                                (stats?.avg_cer ?? 0) < 0.05
                                    ? 'text-green-600'
                                    : (stats?.avg_cer ?? 0) < 0.1
                                      ? 'text-yellow-600'
                                      : 'text-red-600'
                            }`}
                        >
                            {stats?.avg_cer !== undefined
                                ? `${(stats.avg_cer * 100).toFixed(2)}%`
                                : '-'}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            WER (Word Error Rate)
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p
                            className={`text-3xl font-bold ${
                                (stats?.avg_wer ?? 0) < 0.1
                                    ? 'text-green-600'
                                    : (stats?.avg_wer ?? 0) < 0.2
                                      ? 'text-yellow-600'
                                      : 'text-red-600'
                            }`}
                        >
                            {stats?.avg_wer !== undefined
                                ? `${(stats.avg_wer * 100).toFixed(2)}%`
                                : '-'}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            Umlaut-Genauigkeit
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p
                            className={`text-3xl font-bold ${
                                (stats?.avg_umlaut_accuracy ?? 0) >= 0.99
                                    ? 'text-green-600'
                                    : (stats?.avg_umlaut_accuracy ?? 0) >= 0.95
                                      ? 'text-yellow-600'
                                      : 'text-red-600'
                            }`}
                        >
                            {stats?.avg_umlaut_accuracy !== undefined
                                ? `${(stats.avg_umlaut_accuracy * 100).toFixed(1)}%`
                                : '-'}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">
                            Verarbeitete Samples
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-3xl font-bold">
                            {stats?.samples_processed?.toLocaleString('de-DE') ?? 0}
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* System Info */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            {config.requiresGPU ? (
                                <Zap className="h-4 w-4 text-yellow-500" />
                            ) : (
                                <Cpu className="h-4 w-4 text-blue-500" />
                            )}
                            Hardware
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        <div className="flex justify-between">
                            <span className="text-muted-foreground">Typ</span>
                            <span className="font-medium">
                                {config.requiresGPU ? 'GPU-beschleunigt' : 'CPU-basiert'}
                            </span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-muted-foreground">VRAM-Bedarf</span>
                            <span className="font-medium">{config.vramGB} GB</span>
                        </div>
                        <Progress value={(config.vramGB / 16) * 100} className="h-2" />
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                            Staerken
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ul className="space-y-1">
                            {config.strengths.map((s) => (
                                <li key={s} className="text-sm flex items-center gap-2">
                                    <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
                                    {s}
                                </li>
                            ))}
                        </ul>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <AlertCircle className="h-4 w-4 text-yellow-500" />
                            Schwaechen
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ul className="space-y-1">
                            {config.weaknesses.map((w) => (
                                <li key={w} className="text-sm flex items-center gap-2">
                                    <div className="w-1.5 h-1.5 rounded-full bg-yellow-500" />
                                    {w}
                                </li>
                            ))}
                        </ul>
                    </CardContent>
                </Card>
            </div>

            {/* Tabs */}
            <Tabs defaultValue="trends" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="trends">
                        <TrendingUp className="mr-2 h-4 w-4" />
                        Performance-Trends
                    </TabsTrigger>
                    <TabsTrigger value="samples">
                        <FileText className="mr-2 h-4 w-4" />
                        Stichproben
                    </TabsTrigger>
                    <TabsTrigger value="metrics">
                        <Clock className="mr-2 h-4 w-4" />
                        Detaillierte Metriken
                    </TabsTrigger>
                </TabsList>

                {/* Trends Tab */}
                <TabsContent value="trends">
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle>Performance-Trend</CardTitle>
                                    <CardDescription>
                                        CER, WER und Umlaut-Genauigkeit ueber Zeit
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
                            {chartData.length > 0 ? (
                                <div className="h-[350px]">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <LineChart data={chartData}>
                                            <CartesianGrid strokeDasharray="3 3" />
                                            <XAxis dataKey="date" />
                                            <YAxis domain={[0, 100]} />
                                            <Tooltip
                                                formatter={(value: number) =>
                                                    `${value.toFixed(2)}%`
                                                }
                                            />
                                            <Legend />
                                            <Line
                                                type="monotone"
                                                dataKey="CER"
                                                stroke="#ef4444"
                                                strokeWidth={2}
                                                dot={{ r: 3 }}
                                                name="CER (%)"
                                            />
                                            <Line
                                                type="monotone"
                                                dataKey="WER"
                                                stroke="#f97316"
                                                strokeWidth={2}
                                                dot={{ r: 3 }}
                                                name="WER (%)"
                                            />
                                            <Line
                                                type="monotone"
                                                dataKey="Umlaut"
                                                stroke="#22c55e"
                                                strokeWidth={2}
                                                dot={{ r: 3 }}
                                                name="Umlaut-Genauigkeit (%)"
                                            />
                                        </LineChart>
                                    </ResponsiveContainer>
                                </div>
                            ) : (
                                <div className="h-[350px] flex items-center justify-center text-muted-foreground">
                                    Keine Trend-Daten verfuegbar
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Samples Tab */}
                <TabsContent value="samples">
                    <Card>
                        <CardHeader>
                            <CardTitle>Benchmark-Samples</CardTitle>
                            <CardDescription>
                                Aktuelle Stichproben fuer diesen Backend
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Datei</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Sprache</TableHead>
                                        <TableHead>Merkmale</TableHead>
                                        <TableHead className="text-right">Aktion</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {samplesData?.samples?.slice(0, 10).map((sample) => (
                                        <TableRow key={sample.id}>
                                            <TableCell className="font-medium">
                                                {sample.file_path.split('/').pop()}
                                            </TableCell>
                                            <TableCell>
                                                <Badge
                                                    variant={
                                                        sample.status === 'verified'
                                                            ? 'default'
                                                            : sample.status === 'pending'
                                                              ? 'secondary'
                                                              : 'outline'
                                                    }
                                                >
                                                    {sample.status}
                                                </Badge>
                                            </TableCell>
                                            <TableCell>
                                                <Badge variant="outline">
                                                    {sample.language.toUpperCase()}
                                                </Badge>
                                            </TableCell>
                                            <TableCell>
                                                <div className="flex gap-1">
                                                    {sample.has_umlauts && (
                                                        <Badge variant="secondary" className="text-xs">
                                                            Umlaute
                                                        </Badge>
                                                    )}
                                                    {sample.has_tables && (
                                                        <Badge variant="secondary" className="text-xs">
                                                            Tabellen
                                                        </Badge>
                                                    )}
                                                    {sample.has_fraktur && (
                                                        <Badge variant="secondary" className="text-xs">
                                                            Fraktur
                                                        </Badge>
                                                    )}
                                                </div>
                                            </TableCell>
                                            <TableCell className="text-right">
                                                <Button variant="ghost" size="sm">
                                                    Details
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    )) ?? (
                                        <TableRow>
                                            <TableCell colSpan={5} className="text-center text-muted-foreground">
                                                Keine Samples gefunden
                                            </TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Metrics Tab */}
                <TabsContent value="metrics">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <Card>
                            <CardHeader>
                                <CardTitle>Verteilungs-Metriken</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="flex justify-between items-center">
                                    <span className="text-muted-foreground">P50 CER</span>
                                    <span className="font-medium">
                                        {stats?.p50_cer !== undefined
                                            ? `${(stats.p50_cer * 100).toFixed(2)}%`
                                            : '-'}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-muted-foreground">P90 CER</span>
                                    <span className="font-medium">
                                        {stats?.p90_cer !== undefined
                                            ? `${(stats.p90_cer * 100).toFixed(2)}%`
                                            : '-'}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-muted-foreground">P95 CER</span>
                                    <span className="font-medium">
                                        {stats?.p95_cer !== undefined
                                            ? `${(stats.p95_cer * 100).toFixed(2)}%`
                                            : '-'}
                                    </span>
                                </div>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardHeader>
                                <CardTitle>Performance</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="flex justify-between items-center">
                                    <span className="text-muted-foreground">Durchschn. Zeit</span>
                                    <span className="font-medium">
                                        {stats?.avg_processing_time_ms !== undefined
                                            ? `${stats.avg_processing_time_ms.toFixed(0)} ms`
                                            : '-'}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-muted-foreground">Gelernte Gewichtung</span>
                                    <span className="font-medium">
                                        {weight !== undefined ? `${(weight * 100).toFixed(1)}%` : '-'}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center">
                                    <span className="text-muted-foreground">VRAM-Auslastung</span>
                                    <span className="font-medium">
                                        {config.vramGB} / 16 GB ({((config.vramGB / 16) * 100).toFixed(0)}%)
                                    </span>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </TabsContent>
            </Tabs>
        </div>
    )
}
