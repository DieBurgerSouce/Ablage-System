import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    Activity,
    BarChart3,
    Brain,
    Clock,
    Cpu,
    ExternalLink,
    FileText,
    FlaskConical,
    GitBranch,
    GitCompare,
    Layers,
    Loader2,
    TrendingUp,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { TrainingOverviewStats, BackendStats } from '@/lib/api/services/training';
import { monitoringService } from '@/lib/api/services/monitoring';
import {
    useOverviewStats,
    useBackendStats,
    useBackendComparison,
} from '../hooks/use-training-queries';
import {
    getBackendDisplayName,
    getBackendColor,
} from '../constants/backend-config';
import { BackendComparisonChart } from './BackendComparisonChart';
import { SamplesList } from './SamplesList';
import { BatchesList } from './BatchesList';
import { LearningInsights } from './LearningInsights';

// Icon-Mapping für Grafana Dashboards
const dashboardIcons: Record<string, React.ReactNode> = {
    Activity: <Activity className="h-4 w-4" />,
    FileText: <FileText className="h-4 w-4" />,
    Cpu: <Cpu className="h-4 w-4" />,
    GitBranch: <GitBranch className="h-4 w-4" />,
    Database: <Layers className="h-4 w-4" />,
};

export function TrainingDashboard() {
    const [activeTab, setActiveTab] = useState('overview');

    const { data: stats, isLoading: statsLoading } = useOverviewStats();
    const { data: backendStats, isLoading: backendStatsLoading } = useBackendStats(30);
    const { data: comparison } = useBackendComparison();

    // Grafana Dashboard Links
    const { data: dashboards } = useQuery({
        queryKey: ['monitoring', 'dashboards'],
        queryFn: monitoringService.getDashboards,
        staleTime: 5 * 60 * 1000, // 5 Minuten
    });

    return (
        <div className="space-y-6">
            {/* Header mit Grafana Links */}
            {dashboards?.enabled && (
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-bold">OCR Training Dashboard</h1>
                        <p className="text-muted-foreground">
                            Ground Truth, Benchmarks & Self-Learning
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {dashboards?.dashboards?.ocr_pipeline && (
                            <Button variant="outline" size="sm" asChild>
                                <a
                                    href={dashboards.dashboards.ocr_pipeline.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-1.5"
                                >
                                    {dashboardIcons[dashboards.dashboards.ocr_pipeline.icon] || <Activity className="h-4 w-4" />}
                                    OCR Metriken
                                    <ExternalLink className="h-3 w-3 ml-1" />
                                </a>
                            </Button>
                        )}
                        {dashboards?.dashboards?.ml_routing && (
                            <Button variant="outline" size="sm" asChild>
                                <a
                                    href={dashboards.dashboards.ml_routing.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-1.5"
                                >
                                    {dashboardIcons[dashboards.dashboards.ml_routing.icon] || <GitBranch className="h-4 w-4" />}
                                    ML Routing
                                    <ExternalLink className="h-3 w-3 ml-1" />
                                </a>
                            </Button>
                        )}
                        {dashboards?.dashboards?.gpu_profiling && (
                            <Button variant="outline" size="sm" asChild>
                                <a
                                    href={dashboards.dashboards.gpu_profiling.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-1.5"
                                >
                                    {dashboardIcons[dashboards.dashboards.gpu_profiling.icon] || <Cpu className="h-4 w-4" />}
                                    GPU
                                    <ExternalLink className="h-3 w-3 ml-1" />
                                </a>
                            </Button>
                        )}
                    </div>
                </div>
            )}

        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
            <TabsList className="grid w-full grid-cols-5">
                <TabsTrigger value="overview" className="gap-2">
                    <BarChart3 className="w-4 h-4" />
                    <span className="hidden sm:inline">Übersicht</span>
                </TabsTrigger>
                <TabsTrigger value="comparison" className="gap-2">
                    <GitCompare className="w-4 h-4" />
                    <span className="hidden sm:inline">Backend-Vergleich</span>
                </TabsTrigger>
                <TabsTrigger value="samples" className="gap-2">
                    <FileText className="w-4 h-4" />
                    <span className="hidden sm:inline">Ground Truth</span>
                </TabsTrigger>
                <TabsTrigger value="batches" className="gap-2">
                    <Layers className="w-4 h-4" />
                    <span className="hidden sm:inline">Stichproben</span>
                </TabsTrigger>
                <TabsTrigger value="learning" className="gap-2">
                    <Brain className="w-4 h-4" />
                    <span className="hidden sm:inline">Self-Learning</span>
                </TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-6">
                <OverviewTab
                    stats={stats}
                    backendStats={Array.isArray(backendStats) ? backendStats : []}
                    isLoading={statsLoading || backendStatsLoading}
                />
            </TabsContent>

            <TabsContent value="comparison" className="space-y-6">
                <BackendComparisonChart comparison={comparison} />
            </TabsContent>

            <TabsContent value="samples" className="space-y-6">
                <SamplesList />
            </TabsContent>

            <TabsContent value="batches" className="space-y-6">
                <BatchesList />
            </TabsContent>

            <TabsContent value="learning" className="space-y-6">
                <LearningInsights />
            </TabsContent>
        </Tabs>
        </div>
    );
}

interface OverviewTabProps {
    stats?: TrainingOverviewStats;
    backendStats: BackendStats[];
    isLoading: boolean;
}

function OverviewTab({ stats, backendStats, isLoading }: OverviewTabProps) {
    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="flex items-center gap-3 text-muted-foreground">
                    <Loader2 className="h-6 w-6 animate-spin" />
                    <span>Lade Statistiken...</span>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Stats Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <StatsCard
                    title="Ground Truth Samples"
                    value={stats?.total_samples || 0}
                    icon={<FileText className="w-4 h-4 text-muted-foreground" />}
                    description={`${stats?.verified_samples || 0} verifiziert`}
                />
                <StatsCard
                    title="Ausstehende Annotationen"
                    value={stats?.pending_annotations || 0}
                    icon={<Clock className="w-4 h-4 text-muted-foreground" />}
                    description="Warten auf Bearbeitung"
                    variant={stats?.pending_annotations && stats.pending_annotations > 10 ? 'warning' : 'default'}
                />
                <StatsCard
                    title="Aktive Batches"
                    value={stats?.active_batches || 0}
                    icon={<FlaskConical className="w-4 h-4 text-muted-foreground" />}
                    description="In Bearbeitung"
                />
                <StatsCard
                    title="Korrekturen (24h)"
                    value={stats?.recent_corrections_24h || 0}
                    icon={<TrendingUp className="w-4 h-4 text-muted-foreground" />}
                    description={`${stats?.unprocessed_corrections || 0} unverarbeitet`}
                />
            </div>

            {/* Backend Performance Overview */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <GitCompare className="w-5 h-5" />
                        Backend Performance (letzte 30 Tage)
                    </CardTitle>
                    <CardDescription>
                        Durchschnittliche Qualitätsmetriken pro OCR Backend
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {backendStats.length > 0 ? (
                        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                            {backendStats.map((backend) => (
                                <BackendCard key={backend.backend_name} backend={backend} />
                            ))}
                        </div>
                    ) : (
                        <div className="text-center py-8 text-muted-foreground">
                            Keine Backend-Statistiken verfügbar
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Distribution Charts */}
            <div className="grid gap-6 md:grid-cols-2">
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg">Samples nach Sprache</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3">
                            {Object.entries(stats?.samples_by_language || {}).map(([lang, count]) => (
                                <div key={lang} className="flex items-center justify-between">
                                    <span className="font-medium uppercase">{lang}</span>
                                    <Badge variant="secondary">{count}</Badge>
                                </div>
                            ))}
                            {Object.keys(stats?.samples_by_language || {}).length === 0 && (
                                <p className="text-muted-foreground text-sm text-center py-4">
                                    Keine Daten verfügbar
                                </p>
                            )}
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg">Samples nach Dokumenttyp</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3">
                            {Object.entries(stats?.samples_by_document_type || {}).map(([type, count]) => (
                                <div key={type} className="flex items-center justify-between">
                                    <span className="font-medium capitalize">{type}</span>
                                    <Badge variant="secondary">{count}</Badge>
                                </div>
                            ))}
                            {Object.keys(stats?.samples_by_document_type || {}).length === 0 && (
                                <p className="text-muted-foreground text-sm text-center py-4">
                                    Keine Daten verfügbar
                                </p>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

interface StatsCardProps {
    title: string;
    value: number;
    icon: React.ReactNode;
    description: string;
    variant?: 'default' | 'warning';
}

function StatsCard({ title, value, icon, description, variant = 'default' }: StatsCardProps) {
    return (
        <Card className={variant === 'warning' ? 'border-yellow-500/50 bg-yellow-500/5' : ''}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{title}</CardTitle>
                {icon}
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold">{value.toLocaleString('de-DE')}</div>
                <p className="text-xs text-muted-foreground">{description}</p>
            </CardContent>
        </Card>
    );
}

interface BackendCardProps {
    backend: BackendStats;
}

function BackendCard({ backend }: BackendCardProps) {
    const cerColor = backend.avg_cer !== undefined
        ? backend.avg_cer < 0.05 ? 'text-green-600' : backend.avg_cer < 0.10 ? 'text-yellow-600' : 'text-red-600'
        : 'text-muted-foreground';

    const umlautColor = backend.avg_umlaut_accuracy !== undefined
        ? backend.avg_umlaut_accuracy >= 0.99 ? 'text-green-600' : backend.avg_umlaut_accuracy >= 0.95 ? 'text-yellow-600' : 'text-red-600'
        : 'text-muted-foreground';

    const displayName = getBackendDisplayName(backend.backend_name);
    const color = getBackendColor(backend.backend_name);

    return (
        <div className="rounded-lg border p-4 space-y-3 hover:border-primary/50 transition-colors">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: color }}
                    />
                    <h4 className="font-semibold text-sm">{displayName}</h4>
                </div>
                <Badge variant="outline" className="text-xs">
                    {backend.samples_processed} Samples
                </Badge>
            </div>
            <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                    <span className="text-muted-foreground">CER</span>
                    <span className={cerColor}>
                        {backend.avg_cer != null ? `${(Number(backend.avg_cer) * 100).toFixed(2)}%` : '-'}
                    </span>
                </div>
                <div className="flex justify-between">
                    <span className="text-muted-foreground">WER</span>
                    <span>
                        {backend.avg_wer != null ? `${(Number(backend.avg_wer) * 100).toFixed(2)}%` : '-'}
                    </span>
                </div>
                <div className="flex justify-between">
                    <span className="text-muted-foreground">Umlaut</span>
                    <span className={umlautColor}>
                        {backend.avg_umlaut_accuracy != null ? `${(Number(backend.avg_umlaut_accuracy) * 100).toFixed(1)}%` : '-'}
                    </span>
                </div>
                <div className="flex justify-between">
                    <span className="text-muted-foreground">Zeit</span>
                    <span>
                        {backend.avg_processing_time_ms != null ? `${Number(backend.avg_processing_time_ms).toFixed(0)}ms` : '-'}
                    </span>
                </div>
            </div>
        </div>
    );
}
