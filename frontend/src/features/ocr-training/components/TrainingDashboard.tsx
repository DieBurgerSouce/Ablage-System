import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    BarChart3,
    Clock,
    FileText,
    FlaskConical,
    GitCompare,
    Layers,
    TrendingUp,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { trainingService, type TrainingOverviewStats, type BackendStats } from '@/lib/api/services/training';
import { BackendComparisonChart } from './BackendComparisonChart';
import { SamplesList } from './SamplesList';
import { BatchesList } from './BatchesList';

export function TrainingDashboard() {
    const [activeTab, setActiveTab] = useState('overview');

    const { data: stats, isLoading: statsLoading } = useQuery({
        queryKey: ['training', 'overview'],
        queryFn: trainingService.getOverviewStats,
    });

    const { data: backendStats, isLoading: backendStatsLoading } = useQuery({
        queryKey: ['training', 'backend-stats'],
        queryFn: () => trainingService.getBackendStats(30),
    });

    const { data: comparison } = useQuery({
        queryKey: ['training', 'comparison'],
        queryFn: () => trainingService.getBackendComparison(),
    });

    return (
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
            <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="overview" className="gap-2">
                    <BarChart3 className="w-4 h-4" />
                    Übersicht
                </TabsTrigger>
                <TabsTrigger value="comparison" className="gap-2">
                    <GitCompare className="w-4 h-4" />
                    Backend-Vergleich
                </TabsTrigger>
                <TabsTrigger value="samples" className="gap-2">
                    <FileText className="w-4 h-4" />
                    Ground Truth
                </TabsTrigger>
                <TabsTrigger value="batches" className="gap-2">
                    <Layers className="w-4 h-4" />
                    Stichproben
                </TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-6">
                <OverviewTab
                    stats={stats}
                    backendStats={backendStats || []}
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
        </Tabs>
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
                <div className="animate-pulse text-muted-foreground">Lade Statistiken...</div>
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
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                        {backendStats.map((backend) => (
                            <BackendCard key={backend.backend_name} backend={backend} />
                        ))}
                    </div>
                </CardContent>
            </Card>

            {/* Distribution Charts */}
            <div className="grid gap-6 md:grid-cols-2">
                <Card>
                    <CardHeader>
                        <CardTitle>Samples nach Sprache</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            {Object.entries(stats?.samples_by_language || {}).map(([lang, count]) => (
                                <div key={lang} className="flex items-center justify-between">
                                    <span className="font-medium uppercase">{lang}</span>
                                    <Badge variant="secondary">{count}</Badge>
                                </div>
                            ))}
                            {Object.keys(stats?.samples_by_language || {}).length === 0 && (
                                <p className="text-muted-foreground text-sm">Keine Daten verfügbar</p>
                            )}
                        </div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <CardTitle>Samples nach Dokumenttyp</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-2">
                            {Object.entries(stats?.samples_by_document_type || {}).map(([type, count]) => (
                                <div key={type} className="flex items-center justify-between">
                                    <span className="font-medium capitalize">{type}</span>
                                    <Badge variant="secondary">{count}</Badge>
                                </div>
                            ))}
                            {Object.keys(stats?.samples_by_document_type || {}).length === 0 && (
                                <p className="text-muted-foreground text-sm">Keine Daten verfügbar</p>
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
        <Card className={variant === 'warning' ? 'border-yellow-500/50' : ''}>
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

    return (
        <div className="rounded-lg border p-4 space-y-3">
            <div className="flex items-center justify-between">
                <h4 className="font-semibold text-sm">{backend.backend_name}</h4>
                <Badge variant="outline" className="text-xs">
                    {backend.samples_processed} Samples
                </Badge>
            </div>
            <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                    <span className="text-muted-foreground">CER</span>
                    <span className={cerColor}>
                        {backend.avg_cer !== undefined ? `${(backend.avg_cer * 100).toFixed(2)}%` : '-'}
                    </span>
                </div>
                <div className="flex justify-between">
                    <span className="text-muted-foreground">WER</span>
                    <span>
                        {backend.avg_wer !== undefined ? `${(backend.avg_wer * 100).toFixed(2)}%` : '-'}
                    </span>
                </div>
                <div className="flex justify-between">
                    <span className="text-muted-foreground">Umlaut</span>
                    <span className={umlautColor}>
                        {backend.avg_umlaut_accuracy !== undefined ? `${(backend.avg_umlaut_accuracy * 100).toFixed(1)}%` : '-'}
                    </span>
                </div>
                <div className="flex justify-between">
                    <span className="text-muted-foreground">Zeit</span>
                    <span>
                        {backend.avg_processing_time_ms !== undefined ? `${backend.avg_processing_time_ms}ms` : '-'}
                    </span>
                </div>
            </div>
        </div>
    );
}
