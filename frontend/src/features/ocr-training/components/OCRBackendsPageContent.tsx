import { Link } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
    ArrowRight,
    Cpu,
    Zap,
    Trophy,
    BarChart3,
    Activity,
    Clock,
    FileText,
    Loader2,
    AlertCircle,
} from 'lucide-react';
import {
    RadarChart,
    PolarGrid,
    PolarAngleAxis,
    PolarRadiusAxis,
    Radar,
    ResponsiveContainer,
    Legend,
} from 'recharts';
import {
    BACKEND_CONFIG,
    BACKEND_IDS,
    getBackendDisplayName,
    MAX_VRAM_GB,
} from '@/features/ocr-training/constants/backend-config';
import {
    useBackendComparison,
    useLearnedWeights,
} from '@/features/ocr-training/hooks/use-training-queries';
import { RunBenchmarkDialog } from '@/features/ocr-training/components/RunBenchmarkDialog';

export function OCRBackendsPageContent() {
    const { data: comparison, isLoading: comparisonLoading, error: comparisonError } = useBackendComparison();
    const { data: learnedWeights, isLoading: weightsLoading } = useLearnedWeights();

    const isLoading = comparisonLoading || weightsLoading;

    // Radar Chart Daten vorbereiten - defensive Check für comparison.backends
    const radarData = comparison?.backends ? [
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
    ] : [];

    // Loading State
    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="flex items-center gap-3 text-muted-foreground">
                    <Loader2 className="h-6 w-6 animate-spin" />
                    <span>Lade Backend-Daten...</span>
                </div>
            </div>
        );
    }

    // Error State
    if (comparisonError) {
        return (
            <div className="flex items-center justify-center h-64">
                <Card className="max-w-md">
                    <CardContent className="pt-6">
                        <div className="flex items-start gap-3">
                            <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
                            <div>
                                <p className="font-medium">Fehler beim Laden</p>
                                <p className="text-sm text-muted-foreground mt-1">
                                    Die Backend-Daten konnten nicht geladen werden.
                                    Bitte versuchen Sie es später erneut.
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>
        );
    }

    return (
        <div className="space-y-8">
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
                <RunBenchmarkDialog />
            </div>

            {/* Backend Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {BACKEND_IDS.map((backendId) => {
                    const config = BACKEND_CONFIG[backendId];
                    const stats = comparison?.backends[backendId];
                    const weight = learnedWeights?.weights?.[backendId];
                    const isBestBackend = comparison?.best_backend === backendId;

                    return (
                        <Link
                            key={backendId}
                            to="/admin/ocr-backends/$backend"
                            params={{ backend: backendId }}
                            className="block"
                        >
                            <Card
                                className={`hover:border-primary/50 transition-colors cursor-pointer h-full ${
                                    isBestBackend ? 'ring-2 ring-green-500/30 bg-green-500/5' : ''
                                }`}
                            >
                                <CardHeader className="pb-2">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            <div
                                                className="w-3 h-3 rounded-full flex-shrink-0"
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
                                    {/* Hardware Info */}
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
                                                value={(config.vramGB / MAX_VRAM_GB) * 100}
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
                                                        Number(stats.avg_cer ?? 0) < 0.05
                                                            ? 'text-green-600'
                                                            : Number(stats.avg_cer ?? 0) < 0.1
                                                              ? 'text-yellow-600'
                                                              : 'text-red-600'
                                                    }`}
                                                >
                                                    {stats.avg_cer !== undefined
                                                        ? `${(Number(stats.avg_cer) * 100).toFixed(1)}%`
                                                        : '-'}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-xs text-muted-foreground">Umlaut</p>
                                                <p
                                                    className={`text-lg font-semibold ${
                                                        Number(stats.avg_umlaut_accuracy ?? 0) >= 0.99
                                                            ? 'text-green-600'
                                                            : Number(stats.avg_umlaut_accuracy ?? 0) >= 0.95
                                                              ? 'text-yellow-600'
                                                              : 'text-red-600'
                                                    }`}
                                                >
                                                    {stats.avg_umlaut_accuracy !== undefined
                                                        ? `${(Number(stats.avg_umlaut_accuracy) * 100).toFixed(0)}%`
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
                                        <div className="py-4 text-center text-muted-foreground text-sm border-t">
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
                                                {(Number(weight) * 100).toFixed(0)}%
                                            </Badge>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </Link>
                    );
                })}
            </div>

            {/* Radar Chart Vergleich */}
            {comparison?.backends && Object.keys(comparison.backends).length > 0 && (
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
                                    {BACKEND_IDS.map((backendId) => (
                                        <Radar
                                            key={backendId}
                                            name={getBackendDisplayName(backendId)}
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
                        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                            <FileText className="h-4 w-4" />
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
                        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                            <Trophy className="h-4 w-4" />
                            Bester Backend
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-2xl font-bold">
                            {comparison?.best_backend
                                ? getBackendDisplayName(comparison.best_backend)
                                : '-'}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                            <Clock className="h-4 w-4" />
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
                        <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                            <Activity className="h-4 w-4" />
                            Konfidenz
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-2xl font-bold">
                            {learnedWeights?.confidence !== undefined
                                ? `${(Number(learnedWeights.confidence) * 100).toFixed(0)}%`
                                : '-'}
                        </p>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
