/**
 * Proactive Insights Widget für Dashboard
 *
 * Zeigt KI-generierte Erkenntnisse und Handlungsempfehlungen:
 * - Skonto-Fristen
 * - Duplikat-Warnungen
 * - Risiko-Alerts
 * - Workflow-Optimierungen
 * - Datenqualitäts-Hinweise
 */

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError, QueryErrorAlert, KPICard } from '../shared';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
    Lightbulb,
    AlertTriangle,
    Clock,
    TrendingUp,
    ChevronRight,
    Sparkles,
    AlertCircle,
    CheckCircle2,
    Info
} from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { api } from '@/lib/api';

// Types
interface RelatedEntity {
    entity_type: string;
    entity_id?: string;
    entity_name: string;
    confidence: number;
}

interface Insight {
    id: string;
    insight_type: string;
    priority: 'critical' | 'high' | 'medium' | 'low';
    title: string;
    message: string;
    detail: string;
    related_entities: RelatedEntity[];
    potential_value?: number;
    action_url?: string;
    action_label?: string;
    expires_at?: string;
    source_rule?: string;
    confidence: number;
    created_at: string;
}

interface InsightSummary {
    total_insights: number;
    critical_count: number;
    high_count: number;
    medium_count: number;
    low_count: number;
    by_category: Record<string, number>;
    total_potential_value: number;
    data_quality_score?: number;
}

interface InsightListResponse {
    insights: Insight[];
    total_count: number;
    by_priority: Record<string, number>;
    by_type: Record<string, number>;
}

// API hooks
function useInsightsSummary() {
    return useQuery({
        queryKey: ['insights', 'summary'],
        queryFn: async (): Promise<InsightSummary> => {
            const response = await api.get('/api/v1/insights/summary');
            return response.data;
        },
        staleTime: 5 * 60 * 1000, // 5 minutes
        refetchInterval: 5 * 60 * 1000, // Refresh every 5 minutes
    });
}

function useTopInsights(limit: number = 5) {
    return useQuery({
        queryKey: ['insights', 'all', { limit }],
        queryFn: async (): Promise<InsightListResponse> => {
            const response = await api.get('/api/v1/insights/all', {
                params: { limit, priority: 'high,critical' },
            });
            return response.data;
        },
        staleTime: 2 * 60 * 1000, // 2 minutes
    });
}

// Helper functions
const formatCurrency = (value: number): string => {
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(value);
};

const getPriorityColor = (priority: string): string => {
    switch (priority) {
        case 'critical':
            return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
        case 'high':
            return 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200';
        case 'medium':
            return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
        case 'low':
            return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
        default:
            return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200';
    }
};

const getPriorityLabel = (priority: string): string => {
    switch (priority) {
        case 'critical':
            return 'Kritisch';
        case 'high':
            return 'Hoch';
        case 'medium':
            return 'Mittel';
        case 'low':
            return 'Niedrig';
        default:
            return priority;
    }
};

const getInsightIcon = (type: string) => {
    switch (type) {
        case 'reminder':
        case 'deadline':
            return Clock;
        case 'warning':
        case 'anomaly':
            return AlertTriangle;
        case 'opportunity':
        case 'optimization':
            return TrendingUp;
        case 'suggestion':
        case 'data_quality':
            return Info;
        default:
            return Lightbulb;
    }
};

// Components
function InsightCard({ insight }: { insight: Insight }) {
    const Icon = getInsightIcon(insight.insight_type);

    return (
        <Card className="hover:bg-accent/50 transition-colors">
            <CardContent className="p-4">
                <div className="flex items-start gap-3">
                    <div className={`p-2 rounded-lg ${
                        insight.priority === 'critical' ? 'bg-red-100 dark:bg-red-900/30' :
                        insight.priority === 'high' ? 'bg-orange-100 dark:bg-orange-900/30' :
                        'bg-blue-100 dark:bg-blue-900/30'
                    }`}>
                        <Icon className={`h-4 w-4 ${
                            insight.priority === 'critical' ? 'text-red-600' :
                            insight.priority === 'high' ? 'text-orange-600' :
                            'text-blue-600'
                        }`} />
                    </div>

                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                            <h4 className="font-medium text-sm truncate">{insight.title}</h4>
                            <Badge variant="outline" className={`text-xs ${getPriorityColor(insight.priority)}`}>
                                {getPriorityLabel(insight.priority)}
                            </Badge>
                        </div>

                        <p className="text-sm text-muted-foreground line-clamp-2">
                            {insight.message}
                        </p>

                        {insight.potential_value && insight.potential_value > 0 && (
                            <p className="text-sm font-medium text-green-600 mt-1">
                                Potenzial: {formatCurrency(insight.potential_value)}
                            </p>
                        )}

                        {insight.action_url && (
                            <Link
                                to={insight.action_url}
                                className="inline-flex items-center text-sm text-primary hover:underline mt-2"
                            >
                                {insight.action_label || 'Details anzeigen'}
                                <ChevronRight className="h-4 w-4 ml-1" />
                            </Link>
                        )}
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

export function ProactiveInsightsWidget() {
    const {
        data: summary,
        isLoading: summaryLoading,
        isError: summaryError,
        error: summaryErrorObj,
        refetch: refetchSummary,
    } = useInsightsSummary();

    const {
        data: topInsights,
        isLoading: insightsLoading,
        isError: insightsError,
    } = useTopInsights(5);

    const isLoading = summaryLoading || insightsLoading;
    const isError = summaryError || insightsError;

    // Calculate stats
    const stats = useMemo(() => {
        if (!summary) {
            return {
                total: 0,
                critical: 0,
                high: 0,
                potentialValue: 0,
                dataQuality: null,
            };
        }

        return {
            total: summary.total_insights,
            critical: summary.critical_count,
            high: summary.high_count,
            potentialValue: summary.total_potential_value,
            dataQuality: summary.data_quality_score,
        };
    }, [summary]);

    const getTrend = (critical: number, high: number): 'positive' | 'warning' | 'neutral' => {
        if (critical > 0) return 'warning';
        if (high > 3) return 'warning';
        if (high > 0) return 'neutral';
        return 'positive';
    };

    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Proaktive Insights" />}
            errorTitle="Insights Fehler"
            errorDescription="Die Insights konnten nicht geladen werden."
        >
            <section className="space-y-4" aria-labelledby="insights-heading">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-primary" />
                        <h2 id="insights-heading" className="text-xl font-semibold">
                            KI-Insights
                        </h2>
                    </div>
                    <Link
                        to="/insights"
                        className="text-sm text-primary hover:underline flex items-center"
                    >
                        Alle anzeigen
                        <ChevronRight className="h-4 w-4 ml-1" />
                    </Link>
                </div>

                {/* Kritische Warnung */}
                {stats.critical > 0 && (
                    <Alert variant="destructive">
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>
                            <strong>{stats.critical} kritische{stats.critical > 1 ? '' : 'r'} Insight{stats.critical > 1 ? 's' : ''}</strong> erfordert sofortige Aufmerksamkeit!
                        </AlertDescription>
                    </Alert>
                )}

                {isError ? (
                    <QueryErrorAlert
                        title="Insights nicht verfügbar"
                        error={summaryErrorObj as Error}
                        onRetry={() => refetchSummary()}
                    />
                ) : isLoading ? (
                    <>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                            {[1, 2, 3, 4].map((i) => (
                                <Skeleton key={i} className="h-32 rounded-xl" />
                            ))}
                        </div>
                        <div className="space-y-3">
                            {[1, 2, 3].map((i) => (
                                <Skeleton key={i} className="h-24 rounded-lg" />
                            ))}
                        </div>
                    </>
                ) : (
                    <>
                        {/* KPI Cards */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                            <KPICard
                                title="Aktive Insights"
                                value={stats.total}
                                icon={Lightbulb}
                                trend={getTrend(stats.critical, stats.high)}
                                subtext={stats.critical > 0 ? `${stats.critical} kritisch` : 'Alles im Blick'}
                                href="/insights"
                                isCurrency={false}
                            />
                            <KPICard
                                title="Handlungsbedarf"
                                value={stats.critical + stats.high}
                                icon={AlertTriangle}
                                trend={stats.critical > 0 ? 'warning' : stats.high > 0 ? 'neutral' : 'positive'}
                                subtext={stats.critical > 0 ? 'Sofort prüfen!' : 'Hohe Priorität'}
                                href="/insights?priority=high,critical"
                                isCurrency={false}
                            />
                            <KPICard
                                title="Einsparpotenzial"
                                value={stats.potentialValue}
                                icon={TrendingUp}
                                trend={stats.potentialValue > 500 ? 'positive' : 'neutral'}
                                subtext="durch Optimierung"
                                href="/insights?type=opportunity"
                            />
                            {stats.dataQuality !== null && (
                                <KPICard
                                    title="Datenqualität"
                                    value={stats.dataQuality}
                                    icon={stats.dataQuality >= 80 ? CheckCircle2 : Info}
                                    trend={stats.dataQuality >= 80 ? 'positive' : stats.dataQuality >= 60 ? 'neutral' : 'warning'}
                                    subtext={stats.dataQuality >= 80 ? 'Sehr gut' : stats.dataQuality >= 60 ? 'Verbesserbar' : 'Optimierungsbedarf'}
                                    href="/insights?type=data_quality"
                                    isCurrency={false}
                                    isPercent={true}
                                />
                            )}
                        </div>

                        {/* Top Insights List */}
                        {topInsights?.insights && topInsights.insights.length > 0 && (
                            <div className="space-y-3">
                                <h3 className="text-sm font-medium text-muted-foreground">
                                    Wichtigste Erkenntnisse
                                </h3>
                                {topInsights.insights.slice(0, 5).map((insight) => (
                                    <InsightCard key={insight.id} insight={insight} />
                                ))}
                            </div>
                        )}

                        {/* Empty State */}
                        {(!topInsights?.insights || topInsights.insights.length === 0) && stats.total === 0 && (
                            <Card className="bg-green-50 dark:bg-green-950 border-green-200 dark:border-green-800">
                                <CardContent className="p-6 text-center">
                                    <CheckCircle2 className="h-12 w-12 text-green-600 mx-auto mb-3" />
                                    <h3 className="font-medium text-green-800 dark:text-green-200 mb-1">
                                        Alles in Ordnung!
                                    </h3>
                                    <p className="text-sm text-green-600 dark:text-green-400">
                                        Aktuell gibt es keine wichtigen Erkenntnisse oder Handlungsempfehlungen.
                                    </p>
                                </CardContent>
                            </Card>
                        )}
                    </>
                )}
            </section>
        </ErrorBoundary>
    );
}
