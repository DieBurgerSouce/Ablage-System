import { useState } from 'react';
import { createFileRoute, Link } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    ArrowLeft,
    Cpu,
    Zap,
    Trophy,
    TrendingUp,
    FileText,
    AlertCircle,
    CheckCircle2,
    Clock,
    Loader2,
    Eye,
    BarChart3,
} from 'lucide-react';
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from 'recharts';
import {
    getBackendConfig,
    MAX_VRAM_GB,
} from '@/features/ocr-training/constants/backend-config';
import {
    useBackendComparison,
    useLearnedWeights,
    useTrendData,
    useSamples,
    useSampleBenchmarks,
} from '@/features/ocr-training/hooks/use-training-queries';
import { RunBenchmarkDialog } from '@/features/ocr-training/components/RunBenchmarkDialog';
import { SampleDetailModal } from '@/features/ocr-training/components/SampleDetailModal';
import type { TrainingSample } from '@/lib/api/services/training';

export const Route = createFileRoute('/admin/ocr-backends/$backend')({
    component: BackendDetailPage,
});

function BackendDetailPage() {
    const { backend } = Route.useParams();
    const [trendDays, setTrendDays] = useState<7 | 30 | 90>(30);
    const [selectedSample, setSelectedSample] = useState<TrainingSample | null>(null);
    const [isDetailOpen, setIsDetailOpen] = useState(false);

    // Backend-Konfiguration mit Fallback
    const config = getBackendConfig(backend) ?? {
        displayName: backend,
        vramGB: 0,
        requiresGPU: false,
        color: '#666',
        description: 'Unbekanntes Backend',
        strengths: [],
        weaknesses: [],
    };

    // Queries
    const { data: comparison, isLoading: comparisonLoading } = useBackendComparison();
    const { data: learnedWeights } = useLearnedWeights();
    const { data: trendData, isLoading: trendLoading } = useTrendData({ backend, days: trendDays });
    const { data: samplesData, isLoading: samplesLoading } = useSamples({
        limit: 20,
        verified_only: true,
    });

    // Sample-Benchmarks für Modal
    const { data: sampleBenchmarks } = useSampleBenchmarks(
        selectedSample?.id ?? '',
        !!selectedSample && isDetailOpen
    );

    const stats = comparison?.backends[backend];
    const weight = learnedWeights?.weights?.[backend];
    const isBestBackend = comparison?.best_backend === backend;

    // Trend-Daten für Chart vorbereiten
    const chartData = trendData?.map((point) => ({
        date: new Date(point.date).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }),
        CER: point.avg_cer !== undefined ? point.avg_cer * 100 : null,
        WER: point.avg_wer !== undefined ? point.avg_wer * 100 : null,
        Umlaut: point.avg_umlaut_accuracy !== undefined ? point.avg_umlaut_accuracy * 100 : null,
    })) ?? [];

    // Loading State
    if (comparisonLoading) {
        return (
            <div className="max-w-7xl mx-auto p-8">
                <div className="flex items-center justify-center h-64">
                    <div className="flex items-center gap-3 text-muted-foreground">
                        <Loader2 className="h-6 w-6 animate-spin" />
                        <span>Lade Backend-Details...</span>
                    </div>
                </div>
            </div>
        );
    }

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
                            className="w-4 h-4 rounded-full flex-shrink-0"
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
                <RunBenchmarkDialog preselectedBackend={backend} />
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
                                Number(stats?.avg_cer ?? 0) < 0.05
                                    ? 'text-green-600'
                                    : Number(stats?.avg_cer ?? 0) < 0.1
                                      ? 'text-yellow-600'
                                      : 'text-red-600'
                            }`}
                        >
                            {stats?.avg_cer !== undefined
                                ? `${(Number(stats.avg_cer) * 100).toFixed(2)}%`
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
                                Number(stats?.avg_wer ?? 0) < 0.1
                                    ? 'text-green-600'
                                    : Number(stats?.avg_wer ?? 0) < 0.2
                                      ? 'text-yellow-600'
                                      : 'text-red-600'
                            }`}
                        >
                            {stats?.avg_wer !== undefined
                                ? `${(Number(stats.avg_wer) * 100).toFixed(2)}%`
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
                                Number(stats?.avg_umlaut_accuracy ?? 0) >= 0.99
                                    ? 'text-green-600'
                                    : Number(stats?.avg_umlaut_accuracy ?? 0) >= 0.95
                                      ? 'text-yellow-600'
                                      : 'text-red-600'
                            }`}
                        >
                            {stats?.avg_umlaut_accuracy !== undefined
                                ? `${(Number(stats.avg_umlaut_accuracy) * 100).toFixed(1)}%`
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
                    <CardContent className="space-y-3">
                        <div className="flex justify-between">
                            <span className="text-muted-foreground">Typ</span>
                            <Badge variant={config.requiresGPU ? 'default' : 'secondary'}>
                                {config.requiresGPU ? 'GPU' : 'CPU'}
                            </Badge>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-muted-foreground">VRAM-Bedarf</span>
                            <span className="font-medium">{config.vramGB} GB</span>
                        </div>
                        <div className="space-y-1">
                            <Progress value={(config.vramGB / MAX_VRAM_GB) * 100} className="h-2" />
                            <p className="text-xs text-muted-foreground text-right">
                                von {MAX_VRAM_GB} GB (RTX 4080)
                            </p>
                        </div>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <CheckCircle2 className="h-4 w-4 text-green-500" />
                            Stärken
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ul className="space-y-1.5">
                            {config.strengths.map((s) => (
                                <li key={s} className="text-sm flex items-center gap-2">
                                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
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
                            Schwächen
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ul className="space-y-1.5">
                            {config.weaknesses.map((w) => (
                                <li key={w} className="text-sm flex items-center gap-2">
                                    <div className="w-1.5 h-1.5 rounded-full bg-yellow-500 flex-shrink-0" />
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
                    <TabsTrigger value="trends" className="gap-2">
                        <TrendingUp className="h-4 w-4" />
                        Performance-Trends
                    </TabsTrigger>
                    <TabsTrigger value="samples" className="gap-2">
                        <FileText className="h-4 w-4" />
                        Stichproben
                    </TabsTrigger>
                    <TabsTrigger value="metrics" className="gap-2">
                        <BarChart3 className="h-4 w-4" />
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
                                        CER, WER und Umlaut-Genauigkeit über Zeit
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
                            {trendLoading ? (
                                <div className="h-[350px] flex items-center justify-center">
                                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                                </div>
                            ) : chartData.length > 0 ? (
                                <div className="h-[350px]">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <LineChart data={chartData}>
                                            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                                            <XAxis dataKey="date" className="text-xs" />
                                            <YAxis domain={[0, 100]} className="text-xs" />
                                            <Tooltip
                                                formatter={(value: number) => `${Number(value).toFixed(2)}%`}
                                                contentStyle={{
                                                    backgroundColor: 'hsl(var(--card))',
                                                    border: '1px solid hsl(var(--border))',
                                                    borderRadius: '6px',
                                                }}
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
                                    Keine Trend-Daten verfügbar
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
                                Verifizierte Samples für Backend-Vergleich
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {samplesLoading ? (
                                <div className="h-64 flex items-center justify-center">
                                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                                </div>
                            ) : (
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
                                        {samplesData?.samples?.length ? (
                                            samplesData.samples.map((sample) => (
                                                <TableRow key={sample.id} className="hover:bg-muted/50">
                                                    <TableCell className="font-medium">
                                                        <div className="flex items-center gap-2">
                                                            <FileText className="h-4 w-4 text-muted-foreground" />
                                                            <span className="truncate max-w-[200px]">
                                                                {sample.file_path.split('/').pop()}
                                                            </span>
                                                        </div>
                                                    </TableCell>
                                                    <TableCell>
                                                        <Badge
                                                            variant={
                                                                sample.status === 'verified'
                                                                    ? 'default'
                                                                    : sample.status === 'annotated'
                                                                      ? 'secondary'
                                                                      : 'outline'
                                                            }
                                                            className={
                                                                sample.status === 'verified'
                                                                    ? 'bg-green-600'
                                                                    : ''
                                                            }
                                                        >
                                                            {sample.status === 'verified' && (
                                                                <CheckCircle2 className="mr-1 h-3 w-3" />
                                                            )}
                                                            {sample.status === 'verified' ? 'Verifiziert' :
                                                             sample.status === 'annotated' ? 'Annotiert' :
                                                             sample.status === 'pending' ? 'Ausstehend' : sample.status}
                                                        </Badge>
                                                    </TableCell>
                                                    <TableCell>
                                                        <Badge variant="outline">
                                                            {sample.language.toUpperCase()}
                                                        </Badge>
                                                    </TableCell>
                                                    <TableCell>
                                                        <div className="flex gap-1 flex-wrap">
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
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            onClick={() => {
                                                                setSelectedSample(sample);
                                                                setIsDetailOpen(true);
                                                            }}
                                                        >
                                                            <Eye className="mr-1 h-4 w-4" />
                                                            Details
                                                        </Button>
                                                    </TableCell>
                                                </TableRow>
                                            ))
                                        ) : (
                                            <TableRow>
                                                <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                                                    Keine Samples gefunden
                                                </TableCell>
                                            </TableRow>
                                        )}
                                    </TableBody>
                                </Table>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Metrics Tab */}
                <TabsContent value="metrics">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <BarChart3 className="h-5 w-5" />
                                    Verteilungs-Metriken
                                </CardTitle>
                                <CardDescription>
                                    Perzentile der Character Error Rate
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="flex justify-between items-center py-2 border-b">
                                    <span className="text-muted-foreground">P50 CER (Median)</span>
                                    <span className="font-medium text-lg">
                                        {stats?.p50_cer !== undefined
                                            ? `${(Number(stats.p50_cer) * 100).toFixed(2)}%`
                                            : '-'}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center py-2 border-b">
                                    <span className="text-muted-foreground">P90 CER</span>
                                    <span className="font-medium text-lg">
                                        {stats?.p90_cer !== undefined
                                            ? `${(Number(stats.p90_cer) * 100).toFixed(2)}%`
                                            : '-'}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center py-2">
                                    <span className="text-muted-foreground">P95 CER</span>
                                    <span className="font-medium text-lg">
                                        {stats?.p95_cer !== undefined
                                            ? `${(Number(stats.p95_cer) * 100).toFixed(2)}%`
                                            : '-'}
                                    </span>
                                </div>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <Clock className="h-5 w-5" />
                                    Performance
                                </CardTitle>
                                <CardDescription>
                                    Verarbeitungszeit und Gewichtung
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="flex justify-between items-center py-2 border-b">
                                    <span className="text-muted-foreground">Durchschn. Verarbeitungszeit</span>
                                    <span className="font-medium text-lg">
                                        {stats?.avg_processing_time_ms !== undefined
                                            ? `${Number(stats.avg_processing_time_ms).toFixed(0)} ms`
                                            : '-'}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center py-2 border-b">
                                    <span className="text-muted-foreground">Gelernte Gewichtung</span>
                                    <div className="flex items-center gap-2">
                                        <span className="font-medium text-lg">
                                            {weight !== undefined ? `${(Number(weight) * 100).toFixed(1)}%` : '-'}
                                        </span>
                                        {isBestBackend && (
                                            <Badge variant="default" className="bg-green-600">
                                                Bester
                                            </Badge>
                                        )}
                                    </div>
                                </div>
                                <div className="flex justify-between items-center py-2">
                                    <span className="text-muted-foreground">VRAM-Auslastung</span>
                                    <span className="font-medium text-lg">
                                        {config.vramGB} / {MAX_VRAM_GB} GB
                                    </span>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </TabsContent>
            </Tabs>

            {/* Sample Detail Modal */}
            {selectedSample && (
                <SampleDetailModal
                    sample={selectedSample}
                    benchmarks={sampleBenchmarks}
                    open={isDetailOpen}
                    onOpenChange={setIsDetailOpen}
                />
            )}
        </div>
    );
}
