/**
 * MLOps Performance Widget fuer Dashboard
 *
 * Zeigt MLOps-Metriken und Modell-Performance:
 * - OCR Accuracy und Confidence
 * - Model-Drift Detection
 * - A/B Test Status
 * - Retraining Status
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary fuer graceful degradation
 * - Konsistente Fehlerbehandlung
 * - Real-time Updates via WebSocket
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
    Brain,
    TrendingUp,
    TrendingDown,
    ChevronRight,
    AlertTriangle,
    CheckCircle2,
    Activity,
    Zap,
    RefreshCw,
    FlaskConical,
    GitBranch,
} from 'lucide-react';

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';

// Types
interface ModelMetrics {
    model_name: string;
    version: string;
    accuracy: number;
    accuracy_change: number;
    confidence_avg: number;
    drift_score: number;
    drift_detected: boolean;
    last_trained: string;
    predictions_today: number;
}

interface ABTestStatus {
    test_id: string;
    name: string;
    status: 'running' | 'completed' | 'pending';
    challenger_improvement: number;
    samples_collected: number;
    samples_target: number;
}

interface RetrainingStatus {
    status: 'idle' | 'scheduled' | 'running' | 'completed' | 'failed';
    next_scheduled: string | null;
    last_completed: string | null;
    pending_corrections: number;
    threshold_reached: boolean;
}

interface MLOpsSummary {
    overall_accuracy: number;
    accuracy_trend: 'up' | 'down' | 'stable';
    models: ModelMetrics[];
    active_ab_tests: ABTestStatus[];
    retraining: RetrainingStatus;
    total_predictions_today: number;
    corrections_rate: number;
}

// API Hook
function useMLOpsPerformance() {
    return useQuery({
        queryKey: ['mlops', 'performance'],
        queryFn: async (): Promise<MLOpsSummary> => {
            const response = await api.get('/api/v1/mlops/performance');
            return response.data;
        },
        staleTime: 60 * 1000, // 1 minute
        refetchInterval: 60 * 1000,
    });
}

// Helper functions
const formatPercent = (value: number): string => {
    return `${(value * 100).toFixed(1)}%`;
};

const formatRelativeTime = (dateString: string | null): string => {
    if (!dateString) return 'Nie';

    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffHours < 1) return 'Gerade eben';
    if (diffHours < 24) return `vor ${diffHours} Std.`;
    if (diffDays < 7) return `vor ${diffDays} Tagen`;

    return date.toLocaleDateString('de-DE');
};

const getAccuracyColor = (accuracy: number): string => {
    if (accuracy >= 0.95) return 'text-green-600';
    if (accuracy >= 0.85) return 'text-yellow-600';
    return 'text-red-600';
};

const getTrendIcon = (trend: string) => {
    switch (trend) {
        case 'up':
            return TrendingUp;
        case 'down':
            return TrendingDown;
        default:
            return Activity;
    }
};

const getTrendColor = (trend: string): string => {
    switch (trend) {
        case 'up':
            return 'text-green-600';
        case 'down':
            return 'text-red-600';
        default:
            return 'text-muted-foreground';
    }
};

const getRetrainingStatusLabel = (status: string): string => {
    const labels: Record<string, string> = {
        idle: 'Bereit',
        scheduled: 'Geplant',
        running: 'Laeuft',
        completed: 'Abgeschlossen',
        failed: 'Fehlgeschlagen',
    };
    return labels[status] || status;
};

const getRetrainingStatusColor = (status: string): string => {
    switch (status) {
        case 'running':
            return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200';
        case 'scheduled':
            return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200';
        case 'completed':
            return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200';
        case 'failed':
            return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200';
        default:
            return 'bg-gray-100 text-gray-800';
    }
};

// Components
function ModelMetricsCard({ model }: { model: ModelMetrics }) {
    const hasDrift = model.drift_detected;

    return (
        <div className={cn(
            'p-3 rounded-lg border',
            hasDrift && 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800',
            !hasDrift && 'bg-muted/30'
        )}>
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <Brain className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">{model.model_name}</span>
                </div>
                <Badge variant="outline" className="text-xs">
                    v{model.version}
                </Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                    <span className="text-muted-foreground">Accuracy: </span>
                    <span className={cn('font-medium', getAccuracyColor(model.accuracy))}>
                        {formatPercent(model.accuracy)}
                    </span>
                </div>
                <div>
                    <span className="text-muted-foreground">Confidence: </span>
                    <span className="font-medium">{formatPercent(model.confidence_avg)}</span>
                </div>
            </div>
            {hasDrift && (
                <div className="flex items-center gap-1 mt-2 text-xs text-yellow-600">
                    <AlertTriangle className="h-3 w-3" />
                    <span>Drift erkannt (Score: {model.drift_score.toFixed(2)})</span>
                </div>
            )}
        </div>
    );
}

function ABTestCard({ test }: { test: ABTestStatus }) {
    const progress = (test.samples_collected / test.samples_target) * 100;
    const isPositive = test.challenger_improvement > 0;

    return (
        <div className="p-2 rounded-lg border bg-muted/30">
            <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1">
                    <FlaskConical className="h-3 w-3 text-muted-foreground" />
                    <span className="text-xs font-medium truncate">{test.name}</span>
                </div>
                <Badge
                    variant="outline"
                    className={cn(
                        'text-xs',
                        test.status === 'running'
                            ? 'bg-blue-100 text-blue-800'
                            : 'bg-gray-100 text-gray-800'
                    )}
                >
                    {test.status === 'running' ? 'Aktiv' : 'Abgeschlossen'}
                </Badge>
            </div>
            <div className="flex items-center justify-between text-xs">
                <Progress value={progress} className="h-1.5 flex-1 mr-2" />
                <span className={cn(
                    'font-medium',
                    isPositive ? 'text-green-600' : 'text-red-600'
                )}>
                    {isPositive ? '+' : ''}{(test.challenger_improvement * 100).toFixed(1)}%
                </span>
            </div>
        </div>
    );
}

function MLOpsPerformanceWidgetContent() {
    // Real-time updates
    useWidgetSubscription('mlops', {
        debounceMs: 1000,
        autoInvalidate: true,
        queryKeysToInvalidate: [['mlops']],
    });

    const {
        data: summary,
        isLoading,
        isError,
    } = useMLOpsPerformance();

    if (isLoading) {
        return (
            <div className="space-y-4">
                <Skeleton className="h-16 rounded-lg" />
                <div className="space-y-2">
                    {[1, 2].map((i) => (
                        <Skeleton key={i} className="h-20 rounded-lg" />
                    ))}
                </div>
            </div>
        );
    }

    if (isError || !summary) {
        return (
            <div className="text-center py-6 text-muted-foreground">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
                <p className="text-sm">MLOps-Daten nicht verfuegbar</p>
            </div>
        );
    }

    const TrendIcon = getTrendIcon(summary.accuracy_trend);
    const hasActiveDrift = summary.models.some(m => m.drift_detected);
    const retrainingNeeded = summary.retraining.threshold_reached;

    return (
        <div className="space-y-4">
            {/* Overall Accuracy */}
            <div className={cn(
                'p-4 rounded-lg border',
                summary.overall_accuracy >= 0.95
                    ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                    : summary.overall_accuracy >= 0.85
                        ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
                        : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
            )}>
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs font-medium text-muted-foreground">
                            Gesamt-Accuracy
                        </p>
                        <p className={cn('text-2xl font-bold', getAccuracyColor(summary.overall_accuracy))}>
                            {formatPercent(summary.overall_accuracy)}
                        </p>
                    </div>
                    <div className={cn('flex items-center gap-1', getTrendColor(summary.accuracy_trend))}>
                        <TrendIcon className="h-5 w-5" />
                        <span className="text-sm font-medium">
                            {summary.accuracy_trend === 'up' ? 'Steigend' :
                             summary.accuracy_trend === 'down' ? 'Fallend' : 'Stabil'}
                        </span>
                    </div>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                    {summary.total_predictions_today.toLocaleString('de-DE')} Vorhersagen heute •
                    {' '}{(summary.corrections_rate * 100).toFixed(1)}% Korrekturrate
                </p>
            </div>

            {/* Alerts */}
            {(hasActiveDrift || retrainingNeeded) && (
                <div className={cn(
                    'p-3 rounded-lg border flex items-center gap-2',
                    'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
                )}>
                    <AlertTriangle className="h-4 w-4 text-yellow-600 shrink-0" />
                    <div className="text-xs">
                        {hasActiveDrift && <p>Model-Drift in {summary.models.filter(m => m.drift_detected).length} Modell(en) erkannt</p>}
                        {retrainingNeeded && <p>{summary.retraining.pending_corrections} Korrekturen - Retraining empfohlen</p>}
                    </div>
                </div>
            )}

            {/* Model Metrics */}
            {summary.models.length > 0 && (
                <div className="space-y-2">
                    <p className="text-xs font-medium text-muted-foreground">
                        Modell-Performance
                    </p>
                    {summary.models.slice(0, 2).map((model) => (
                        <ModelMetricsCard key={model.model_name} model={model} />
                    ))}
                </div>
            )}

            {/* Retraining Status */}
            <div className="p-3 rounded-lg border bg-muted/30">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <RefreshCw className={cn(
                            'h-4 w-4',
                            summary.retraining.status === 'running' && 'animate-spin text-blue-600'
                        )} />
                        <span className="text-sm font-medium">Retraining</span>
                    </div>
                    <Badge
                        variant="outline"
                        className={cn('text-xs', getRetrainingStatusColor(summary.retraining.status))}
                    >
                        {getRetrainingStatusLabel(summary.retraining.status)}
                    </Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                    Letztes Training: {formatRelativeTime(summary.retraining.last_completed)}
                    {summary.retraining.next_scheduled && (
                        <> • Naechstes: {formatRelativeTime(summary.retraining.next_scheduled)}</>
                    )}
                </p>
            </div>

            {/* A/B Tests */}
            {summary.active_ab_tests.length > 0 && (
                <div className="space-y-2">
                    <div className="flex items-center gap-2">
                        <GitBranch className="h-4 w-4 text-muted-foreground" />
                        <p className="text-xs font-medium text-muted-foreground">
                            A/B Tests ({summary.active_ab_tests.filter(t => t.status === 'running').length} aktiv)
                        </p>
                    </div>
                    {summary.active_ab_tests.slice(0, 2).map((test) => (
                        <ABTestCard key={test.test_id} test={test} />
                    ))}
                </div>
            )}

            {/* Link to MLOps page */}
            <Link
                to="/admin/mlops"
                className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
                MLOps Dashboard
                <ChevronRight className="h-4 w-4" />
            </Link>
        </div>
    );
}

export function MLOpsPerformanceWidget() {
    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="MLOps" />}
            errorTitle="MLOps Fehler"
            errorDescription="Die MLOps-Daten konnten nicht geladen werden."
        >
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Brain className="h-5 w-5 text-primary" />
                        MLOps Performance
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <MLOpsPerformanceWidgetContent />
                </CardContent>
            </Card>
        </ErrorBoundary>
    );
}
