import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    RadarChart,
    PolarGrid,
    PolarAngleAxis,
    PolarRadiusAxis,
    Radar,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Trophy, Zap, Target, Timer } from 'lucide-react';
import type { BackendComparison } from '@/lib/api/services/training';
import { getBackendColor } from '../constants/backend-config';
import { useAvailableBackends, useLearnedWeights } from '../hooks/use-training-queries';

interface BackendComparisonChartProps {
    comparison?: BackendComparison;
}

export function BackendComparisonChart({ comparison }: BackendComparisonChartProps) {
    const { data: backends } = useAvailableBackends();
    const { data: learnedWeights } = useLearnedWeights();

    if (!comparison || Object.keys(comparison.backends).length === 0) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Backend-Vergleich</CardTitle>
                    <CardDescription>
                        Noch keine Benchmark-Daten verfügbar. Führen Sie zuerst Benchmarks durch.
                    </CardDescription>
                </CardHeader>
            </Card>
        );
    }

    // Prepare data for bar chart
    const barChartData = Object.entries(comparison.backends).map(([name, data]) => ({
        name,
        CER: data.avg_cer !== undefined ? (data.avg_cer * 100) : 0,
        WER: data.avg_wer !== undefined ? (data.avg_wer * 100) : 0,
        Umlaut: data.avg_umlaut_accuracy !== undefined ? (data.avg_umlaut_accuracy * 100) : 0,
    }));

    // Prepare data for radar chart (normalized scores 0-100)
    const radarData = [
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
    ];


    return (
        <div className="space-y-6">
            {/* Best Backend Highlight */}
            {comparison.best_backend && (
                <Card className="border-green-500/50 bg-green-50/50 dark:bg-green-950/20">
                    <CardHeader className="pb-2">
                        <div className="flex items-center gap-2">
                            <Trophy className="w-5 h-5 text-yellow-500" />
                            <CardTitle className="text-lg">Bestes Backend</CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-2xl font-bold">{comparison.best_backend}</p>
                                <p className="text-sm text-muted-foreground">
                                    Basierend auf {comparison.sample_count} Samples
                                </p>
                            </div>
                            {learnedWeights && (
                                <div className="text-right">
                                    <p className="text-sm text-muted-foreground">Gelernte Gewichtung</p>
                                    <p className="text-xl font-semibold">
                                        {(Number(learnedWeights.weights[comparison.best_backend] || 1) * 100).toFixed(0)}%
                                    </p>
                                </div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Bar Chart - Error Rates */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Target className="w-5 h-5" />
                        Fehlerraten im Vergleich
                    </CardTitle>
                    <CardDescription>
                        CER und WER (niedriger ist besser), Umlaut-Genauigkeit (höher ist besser)
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={barChartData}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" />
                            <YAxis unit="%" />
                            <Tooltip
                                formatter={(value: number) => `${Number(value).toFixed(2)}%`}
                                contentStyle={{
                                    backgroundColor: 'hsl(var(--background))',
                                    border: '1px solid hsl(var(--border))',
                                }}
                            />
                            <Legend />
                            <Bar dataKey="CER" fill="#ef4444" name="CER (Zeichenfehler)" />
                            <Bar dataKey="WER" fill="#f97316" name="WER (Wortfehler)" />
                            <Bar dataKey="Umlaut" fill="#22c55e" name="Umlaut-Genauigkeit" />
                        </BarChart>
                    </ResponsiveContainer>
                </CardContent>
            </Card>

            {/* Radar Chart - Multi-dimensional Comparison */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Zap className="w-5 h-5" />
                        Multidimensionaler Vergleich
                    </CardTitle>
                    <CardDescription>
                        Normalisierte Scores pro Dimension (höher ist besser)
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <ResponsiveContainer width="100%" height={400}>
                        <RadarChart cx="50%" cy="50%" outerRadius="80%" data={radarData}>
                            <PolarGrid />
                            <PolarAngleAxis dataKey="metric" />
                            <PolarRadiusAxis angle={30} domain={[0, 100]} />
                            {Object.keys(comparison.backends).map((backend) => (
                                <Radar
                                    key={backend}
                                    name={backend}
                                    dataKey={backend}
                                    stroke={getBackendColor(backend)}
                                    fill={getBackendColor(backend)}
                                    fillOpacity={0.3}
                                />
                            ))}
                            <Legend />
                            <Tooltip
                                contentStyle={{
                                    backgroundColor: 'hsl(var(--background))',
                                    border: '1px solid hsl(var(--border))',
                                }}
                            />
                        </RadarChart>
                    </ResponsiveContainer>
                </CardContent>
            </Card>

            {/* Detailed Stats Table */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Timer className="w-5 h-5" />
                        Detaillierte Metriken
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b">
                                    <th className="text-left p-2">Backend</th>
                                    <th className="text-right p-2">Samples</th>
                                    <th className="text-right p-2">Ø CER</th>
                                    <th className="text-right p-2">Ø WER</th>
                                    <th className="text-right p-2">Umlaut</th>
                                    <th className="text-right p-2">P50 CER</th>
                                    <th className="text-right p-2">P90 CER</th>
                                    <th className="text-right p-2">Ø Zeit</th>
                                </tr>
                            </thead>
                            <tbody>
                                {Object.entries(comparison.backends).map(([name, data]) => (
                                    <tr key={name} className="border-b hover:bg-muted/50">
                                        <td className="p-2 font-medium">
                                            {name}
                                            {name === comparison.best_backend && (
                                                <Badge variant="default" className="ml-2 text-xs">Best</Badge>
                                            )}
                                        </td>
                                        <td className="text-right p-2">{data.samples_processed}</td>
                                        <td className="text-right p-2">
                                            {data.avg_cer != null ? `${(Number(data.avg_cer) * 100).toFixed(2)}%` : '-'}
                                        </td>
                                        <td className="text-right p-2">
                                            {data.avg_wer != null ? `${(Number(data.avg_wer) * 100).toFixed(2)}%` : '-'}
                                        </td>
                                        <td className="text-right p-2">
                                            {data.avg_umlaut_accuracy != null ? `${(Number(data.avg_umlaut_accuracy) * 100).toFixed(1)}%` : '-'}
                                        </td>
                                        <td className="text-right p-2">
                                            {data.p50_cer != null ? `${(Number(data.p50_cer) * 100).toFixed(2)}%` : '-'}
                                        </td>
                                        <td className="text-right p-2">
                                            {data.p90_cer != null ? `${(Number(data.p90_cer) * 100).toFixed(2)}%` : '-'}
                                        </td>
                                        <td className="text-right p-2">
                                            {data.avg_processing_time_ms != null ? `${data.avg_processing_time_ms}ms` : '-'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>

            {/* Available Backends */}
            {backends && (
                <Card>
                    <CardHeader>
                        <CardTitle>Verfügbare Backends</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                            {backends.map((backend) => (
                                <div
                                    key={backend.name}
                                    className={`rounded-lg border p-4 ${
                                        backend.available ? 'border-green-500/50' : 'border-muted opacity-50'
                                    }`}
                                >
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="font-medium">{backend.display_name}</span>
                                        <Badge variant={backend.available ? 'default' : 'secondary'}>
                                            {backend.available ? 'Aktiv' : 'Inaktiv'}
                                        </Badge>
                                    </div>
                                    <div className="text-sm text-muted-foreground space-y-1">
                                        <p>GPU: {backend.requires_gpu ? `Ja (${backend.vram_gb}GB)` : 'Nein'}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
