/**
 * RelationshipDashboard Component
 *
 * Zeigt eine Übersicht der Geschäftspartner mit:
 * - Zusammenfassungsstatistiken
 * - Top-Kunden und Top-Lieferanten
 * - Dokumenten-Trend-Chart
 * - Entity-Type-Verteilung
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    LayoutDashboard,
    Users,
    Truck,
    FileText,
    UserPlus,
    RefreshCw,
    Loader2,
    PieChart,
} from 'lucide-react';
import {
    PieChart as RechartsPieChart,
    Pie,
    Cell,
    ResponsiveContainer,
    Legend,
    Tooltip,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { TopEntitiesCard } from './TopEntitiesCard';
import { TrendChart } from './TrendChart';
import {
    fetchDashboardStats,
    relationshipsQueryKeys,
    type DashboardPeriod,
} from '../api/relationships-api';

// ==================== Types ====================

interface RelationshipDashboardProps {
    defaultPeriod?: DashboardPeriod;
}

// ==================== Period Labels ====================

const PERIOD_LABELS: Record<DashboardPeriod, string> = {
    '7d': 'Letzte 7 Tage',
    '30d': 'Letzte 30 Tage',
    '90d': 'Letzte 90 Tage',
    '365d': 'Letztes Jahr',
};

// ==================== Entity Type Labels ====================

const ENTITY_TYPE_LABELS: Record<string, string> = {
    customer: 'Kunden',
    supplier: 'Lieferanten',
    both: 'Beides',
    internal: 'Intern',
};

// ==================== Colors ====================

const PIE_COLORS = [
    'hsl(var(--chart-1))',
    'hsl(var(--chart-2))',
    'hsl(var(--chart-3))',
    'hsl(var(--chart-4))',
];

// ==================== Loading Skeleton ====================

function DashboardSkeleton() {
    return (
        <div className="space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[1, 2, 3, 4].map((i) => (
                    <Card key={i}>
                        <CardHeader className="pb-2">
                            <Skeleton className="h-4 w-24" />
                        </CardHeader>
                        <CardContent>
                            <Skeleton className="h-8 w-16" />
                        </CardContent>
                    </Card>
                ))}
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Skeleton className="h-[350px] rounded-lg" />
                <Skeleton className="h-[350px] rounded-lg" />
            </div>

            {/* Top Lists */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Skeleton className="h-[400px] rounded-lg" />
                <Skeleton className="h-[400px] rounded-lg" />
            </div>
        </div>
    );
}

// ==================== Summary Card ====================

interface SummaryCardProps {
    title: string;
    value: number;
    icon: React.ReactNode;
    trend?: string;
}

function SummaryCard({ title, value, icon, trend }: SummaryCardProps) {
    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{title}</CardTitle>
                <div className="text-muted-foreground">{icon}</div>
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold">{value.toLocaleString('de-DE')}</div>
                {trend && (
                    <p className="text-xs text-muted-foreground mt-1">{trend}</p>
                )}
            </CardContent>
        </Card>
    );
}

// ==================== Type Distribution Chart ====================

interface TypeDistributionChartProps {
    data: Record<string, number>;
}

function TypeDistributionChart({ data }: TypeDistributionChartProps) {
    const chartData = Object.entries(data).map(([type, count]) => ({
        name: ENTITY_TYPE_LABELS[type] || type,
        value: count,
    }));

    const total = chartData.reduce((sum, item) => sum + item.value, 0);

    if (total === 0) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="text-lg flex items-center gap-2">
                        <PieChart className="h-5 w-5" />
                        Verteilung nach Typ
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center justify-center h-[200px] text-muted-foreground">
                        Keine Daten verfügbar
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                    <PieChart className="h-5 w-5" />
                    Verteilung nach Typ
                </CardTitle>
                <CardDescription>
                    Geschäftspartner nach Kategorie
                </CardDescription>
            </CardHeader>
            <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                    <RechartsPieChart>
                        <Pie
                            data={chartData}
                            cx="50%"
                            cy="50%"
                            innerRadius={60}
                            outerRadius={90}
                            fill="#8884d8"
                            paddingAngle={2}
                            dataKey="value"
                            label={({ name, percent }) =>
                                `${name} (${(percent * 100).toFixed(0)}%)`
                            }
                            labelLine={false}
                        >
                            {chartData.map((_, index) => (
                                <Cell
                                    key={`cell-${index}`}
                                    fill={PIE_COLORS[index % PIE_COLORS.length]}
                                />
                            ))}
                        </Pie>
                        <Tooltip
                            formatter={(value: number) => [
                                value.toLocaleString('de-DE'),
                                'Anzahl',
                            ]}
                        />
                        <Legend />
                    </RechartsPieChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    );
}

// ==================== Main Component ====================

export function RelationshipDashboard({
    defaultPeriod = '30d',
}: RelationshipDashboardProps) {
    const [period, setPeriod] = useState<DashboardPeriod>(defaultPeriod);

    // Fetch dashboard data
    const {
        data,
        isLoading,
        isError,
        error,
        refetch,
        isFetching,
    } = useQuery({
        queryKey: relationshipsQueryKeys.dashboard(period),
        queryFn: () => fetchDashboardStats(period),
    });

    return (
        <div className="space-y-6">
            {/* Header */}
            <Card>
                <CardHeader>
                    <div className="flex items-start justify-between">
                        <div>
                            <CardTitle className="text-xl flex items-center gap-2">
                                <LayoutDashboard className="h-5 w-5" />
                                Geschäftspartner-Dashboard
                            </CardTitle>
                            <CardDescription>
                                Übersicht der Kunden- und Lieferanten-Aktivität
                            </CardDescription>
                        </div>
                        <div className="flex items-center gap-3">
                            <Select
                                value={period}
                                onValueChange={(value) => setPeriod(value as DashboardPeriod)}
                            >
                                <SelectTrigger className="w-[160px]">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {Object.entries(PERIOD_LABELS).map(([key, label]) => (
                                        <SelectItem key={key} value={key}>
                                            {label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => refetch()}
                                disabled={isFetching}
                            >
                                <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
                            </Button>
                        </div>
                    </div>
                </CardHeader>
            </Card>

            {/* Content */}
            {isLoading ? (
                <DashboardSkeleton />
            ) : isError ? (
                <Card>
                    <CardContent className="py-12 text-center">
                        <p className="text-destructive mb-2">
                            Fehler beim Laden des Dashboards
                        </p>
                        <p className="text-sm text-muted-foreground mb-4">
                            {error instanceof Error ? error.message : 'Unbekannter Fehler'}
                        </p>
                        <Button variant="outline" onClick={() => refetch()}>
                            Erneut versuchen
                        </Button>
                    </CardContent>
                </Card>
            ) : data ? (
                <>
                    {/* Summary Cards */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <SummaryCard
                            title="Kunden"
                            value={data.summary.totalCustomers}
                            icon={<Users className="h-4 w-4" />}
                            trend="Gesamt"
                        />
                        <SummaryCard
                            title="Lieferanten"
                            value={data.summary.totalSuppliers}
                            icon={<Truck className="h-4 w-4" />}
                            trend="Gesamt"
                        />
                        <SummaryCard
                            title="Verknüpfte Dokumente"
                            value={data.summary.linkedDocuments}
                            icon={<FileText className="h-4 w-4" />}
                            trend={PERIOD_LABELS[period as DashboardPeriod]}
                        />
                        <SummaryCard
                            title="Neue Geschäftspartner"
                            value={data.summary.newEntities}
                            icon={<UserPlus className="h-4 w-4" />}
                            trend={PERIOD_LABELS[period as DashboardPeriod]}
                        />
                    </div>

                    {/* Charts Row */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <TrendChart
                            data={data.documentTrend}
                            title="Dokument-Trend"
                            description={`Verknüpfte Dokumente - ${PERIOD_LABELS[period as DashboardPeriod]}`}
                            height={250}
                        />
                        <TypeDistributionChart data={data.typeDistribution} />
                    </div>

                    {/* Top Entities */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <TopEntitiesCard
                            title="Top-Kunden"
                            description={`Nach Dokumentanzahl - ${PERIOD_LABELS[period as DashboardPeriod]}`}
                            entities={data.topCustomers}
                            type="customer"
                            maxItems={10}
                        />
                        <TopEntitiesCard
                            title="Top-Lieferanten"
                            description={`Nach Dokumentanzahl - ${PERIOD_LABELS[period as DashboardPeriod]}`}
                            entities={data.topSuppliers}
                            type="supplier"
                            maxItems={10}
                        />
                    </div>
                </>
            ) : (
                <Card>
                    <CardContent className="py-12 text-center">
                        <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-muted-foreground" />
                        <p className="text-muted-foreground">Dashboard wird geladen...</p>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}

export default RelationshipDashboard;
