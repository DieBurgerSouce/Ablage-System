import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    TrendingUp,
    TrendingDown,
    Minus,
    AlertCircle,
    CheckCircle,
    BarChart3,
    Target,
    Brain,
} from 'lucide-react';
import { useMLDashboard } from '../hooks/use-ml-dashboard';

const ERROR_CATEGORY_LABELS: Record<string, string> = {
    Umlaut: 'Umlaut-Fehler',
    'Digit Swap': 'Zifferntausch',
    Spacing: 'Leerzeichen',
    Case: 'Groß-/Kleinschreibung',
    'OCR Noise': 'OCR-Rauschen',
    Unknown: 'Unbekannt',
};

function LearningCurveSection({ data }: { data: { month?: string; recognition_rate: number; correction_count: number; improvement: number }[] }) {
    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-5 w-5" />
                    Lernfortschritt
                </CardTitle>
                <CardDescription>Entwicklung der Erkennungsrate über Zeit</CardDescription>
            </CardHeader>
            <CardContent>
                <div className="space-y-3">
                    {data.map((point, index) => {
                        const isImproving = point.improvement > 0;
                        const recognitionPercent = Math.round(point.recognition_rate * 100);

                        return (
                            <div
                                key={point.month || index}
                                className="flex items-center justify-between p-3 bg-muted/50 rounded-lg"
                            >
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="font-semibold">{point.month || `Monat ${index + 1}`}</span>
                                        {isImproving ? (
                                            <TrendingUp className="h-4 w-4 text-green-500" />
                                        ) : point.improvement < 0 ? (
                                            <TrendingDown className="h-4 w-4 text-red-500" />
                                        ) : (
                                            <Minus className="h-4 w-4 text-muted-foreground" />
                                        )}
                                    </div>
                                    <div className="grid grid-cols-3 gap-2 text-sm">
                                        <div>
                                            <span className="text-muted-foreground">Erkennungsrate: </span>
                                            <span className="font-semibold">{recognitionPercent}%</span>
                                        </div>
                                        <div>
                                            <span className="text-muted-foreground">Korrekturen: </span>
                                            <span className="font-semibold">{point.correction_count}</span>
                                        </div>
                                        <div>
                                            <span className="text-muted-foreground">Verbesserung: </span>
                                            <span className={`font-semibold ${isImproving ? 'text-green-500' : point.improvement < 0 ? 'text-red-500' : ''}`}>
                                                {point.improvement > 0 ? '+' : ''}{Math.round(point.improvement * 100)}%
                                            </span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </CardContent>
        </Card>
    );
}

function ErrorStatsSection({ stats }: { stats: { total_corrections: number; error_types: { category: string; description: string; count: number; percentage: number }[] } }) {
    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <AlertCircle className="h-5 w-5" />
                    Fehleranalyse
                </CardTitle>
                <CardDescription>
                    Verteilung der Fehlertypen ({stats.total_corrections} Gesamt-Korrekturen)
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="space-y-3">
                    {stats.error_types.map((error) => {
                        const label = ERROR_CATEGORY_LABELS[error.category] || error.category;

                        return (
                            <div key={error.category} className="space-y-1">
                                <div className="flex items-center justify-between">
                                    <div className="flex-1">
                                        <span className="font-medium">{label}</span>
                                        <p className="text-sm text-muted-foreground">{error.description}</p>
                                    </div>
                                    <div className="text-right">
                                        <span className="font-semibold">{error.count}</span>
                                        <p className="text-sm text-muted-foreground">
                                            {Math.round(error.percentage)}%
                                        </p>
                                    </div>
                                </div>
                                <div className="h-2 bg-muted rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-primary rounded-full transition-all"
                                        style={{ width: `${error.percentage}%` }}
                                    ></div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </CardContent>
        </Card>
    );
}

function CorrectionImpactCard({ impact }: { impact: { correction_count: number; avg_confidence_before: number; avg_confidence_after: number; accuracy_improvement_percent: number; summary: string } }) {
    const confidenceBefore = Math.round(impact.avg_confidence_before * 100);
    const confidenceAfter = Math.round(impact.avg_confidence_after * 100);
    const improvement = Math.round(impact.accuracy_improvement_percent);

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Target className="h-5 w-5" />
                    Korrektur-Auswirkung
                </CardTitle>
                <CardDescription>Verbesserung durch Benutzer-Korrekturen</CardDescription>
            </CardHeader>
            <CardContent>
                <div className="space-y-4">
                    <div className="bg-primary/10 border border-primary rounded-lg p-6 text-center">
                        <TrendingUp className="h-8 w-8 mx-auto mb-2 text-primary" />
                        <p className="text-4xl font-bold text-primary">+{improvement}%</p>
                        <p className="text-sm text-muted-foreground mt-1">
                            Genauigkeitsverbesserung
                        </p>
                    </div>

                    <div className="grid grid-cols-3 gap-3">
                        <div className="bg-muted/50 rounded-lg p-3 text-center">
                            <p className="text-2xl font-bold">{impact.correction_count}</p>
                            <p className="text-xs text-muted-foreground">Korrekturen</p>
                        </div>
                        <div className="bg-muted/50 rounded-lg p-3 text-center">
                            <p className="text-2xl font-bold">{confidenceBefore}%</p>
                            <p className="text-xs text-muted-foreground">Vertrauen vorher</p>
                        </div>
                        <div className="bg-muted/50 rounded-lg p-3 text-center">
                            <p className="text-2xl font-bold">{confidenceAfter}%</p>
                            <p className="text-xs text-muted-foreground">Vertrauen nachher</p>
                        </div>
                    </div>

                    {impact.summary && (
                        <Alert>
                            <CheckCircle className="h-4 w-4" />
                            <AlertDescription>{impact.summary}</AlertDescription>
                        </Alert>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

function ModelPerformanceTable({ data }: { data: { document_type: string; document_count: number; correction_count: number; avg_confidence: number; accuracy_rate: number }[] }) {
    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Brain className="h-5 w-5" />
                    Modell-Performance
                </CardTitle>
                <CardDescription>Leistung nach Dokumenttyp</CardDescription>
            </CardHeader>
            <CardContent>
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Dokumenttyp</TableHead>
                            <TableHead className="text-right">Dokumente</TableHead>
                            <TableHead className="text-right">Korrekturen</TableHead>
                            <TableHead className="text-right">Ø Vertrauen</TableHead>
                            <TableHead className="text-right">Genauigkeit</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {data.map((perf) => {
                            const confidence = Math.round(perf.avg_confidence * 100);
                            const accuracy = Math.round(perf.accuracy_rate * 100);
                            const correctionRate = (perf.correction_count / perf.document_count) * 100;

                            return (
                                <TableRow key={perf.document_type}>
                                    <TableCell className="font-medium">{perf.document_type}</TableCell>
                                    <TableCell className="text-right">{perf.document_count}</TableCell>
                                    <TableCell className="text-right">
                                        {perf.correction_count}
                                        <span className="text-xs text-muted-foreground ml-1">
                                            ({Math.round(correctionRate)}%)
                                        </span>
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <Badge variant={confidence >= 90 ? 'default' : confidence >= 70 ? 'secondary' : 'outline'}>
                                            {confidence}%
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <Badge variant={accuracy >= 95 ? 'default' : accuracy >= 85 ? 'secondary' : 'outline'}>
                                            {accuracy}%
                                        </Badge>
                                    </TableCell>
                                </TableRow>
                            );
                        })}
                    </TableBody>
                </Table>
            </CardContent>
        </Card>
    );
}

function CategorizationAccuracyCard({ data }: { data: { total_documents: number; auto_categorized: number; accuracy_rate_percent: number; trend_percent: number; trend_direction: 'up' | 'down' | 'stable' } }) {
    const accuracyPercent = Math.round(data.accuracy_rate_percent);
    const autoRate = Math.round((data.auto_categorized / data.total_documents) * 100);
    const trendPercent = Math.round(data.trend_percent);

    const TrendIcon = data.trend_direction === 'up' ? TrendingUp : data.trend_direction === 'down' ? TrendingDown : Minus;
    const trendColor = data.trend_direction === 'up' ? 'text-green-500' : data.trend_direction === 'down' ? 'text-red-500' : 'text-muted-foreground';

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <CheckCircle className="h-5 w-5" />
                    Auto-Kategorisierung
                </CardTitle>
                <CardDescription>Automatische Dokumentklassifizierung</CardDescription>
            </CardHeader>
            <CardContent>
                <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-muted/50 rounded-lg p-4">
                            <p className="text-3xl font-bold">{accuracyPercent}%</p>
                            <p className="text-sm text-muted-foreground mt-1">Genauigkeit</p>
                            <div className="flex items-center gap-1 mt-2">
                                <TrendIcon className={`h-4 w-4 ${trendColor}`} />
                                <span className={`text-sm font-semibold ${trendColor}`}>
                                    {trendPercent > 0 ? '+' : ''}{trendPercent}%
                                </span>
                            </div>
                        </div>
                        <div className="bg-muted/50 rounded-lg p-4">
                            <p className="text-3xl font-bold">{autoRate}%</p>
                            <p className="text-sm text-muted-foreground mt-1">
                                Auto-kategorisiert
                            </p>
                            <p className="text-xs text-muted-foreground mt-2">
                                {data.auto_categorized} von {data.total_documents}
                            </p>
                        </div>
                    </div>

                    <div className="space-y-1">
                        <div className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground">Fortschritt</span>
                            <span className="font-semibold">{autoRate}%</span>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                                className="h-full bg-primary rounded-full transition-all"
                                style={{ width: `${autoRate}%` }}
                            ></div>
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

export function MLDashboardPage() {
    const [months, setMonths] = useState<number>(6);
    const { data, isLoading, error } = useMLDashboard(months);

    if (isLoading) {
        return (
            <div className="container mx-auto py-8 space-y-6">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold mb-2">ML-Dashboard</h1>
                        <p className="text-muted-foreground">Lade Daten...</p>
                    </div>
                </div>
                <div className="grid gap-6 md:grid-cols-2">
                    {[1, 2, 3, 4].map((i) => (
                        <Card key={i}>
                            <CardContent className="p-6">
                                <div className="animate-pulse space-y-3">
                                    <div className="h-4 bg-muted rounded w-1/3"></div>
                                    <div className="h-32 bg-muted rounded"></div>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="container mx-auto py-8">
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>
                        Dashboard-Daten konnten nicht geladen werden. Bitte versuchen Sie es später erneut.
                    </AlertDescription>
                </Alert>
            </div>
        );
    }

    if (!data) {
        return null;
    }

    return (
        <div className="container mx-auto py-8 space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold mb-2">ML-Dashboard</h1>
                    <p className="text-muted-foreground">
                        Machine Learning Performance & Lernfortschritt
                    </p>
                </div>
                <Select
                    value={months.toString()}
                    onValueChange={(value) => setMonths(parseInt(value, 10))}
                >
                    <SelectTrigger className="w-[180px]">
                        <SelectValue placeholder="Zeitraum wählen" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="3">Letzte 3 Monate</SelectItem>
                        <SelectItem value="6">Letzte 6 Monate</SelectItem>
                        <SelectItem value="12">Letzte 12 Monate</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
                <CorrectionImpactCard impact={data.correction_impact} />
                <CategorizationAccuracyCard data={data.categorization_accuracy} />
            </div>

            <LearningCurveSection data={data.learning_curve} />

            <div className="grid gap-6 md:grid-cols-2">
                <ErrorStatsSection stats={data.error_statistics} />
            </div>

            <ModelPerformanceTable data={data.model_performance_by_type} />
        </div>
    );
}
