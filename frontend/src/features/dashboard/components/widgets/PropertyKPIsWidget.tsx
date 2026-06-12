/**
 * Property KPIs Widget für Dashboard
 *
 * Zeigt Immobilien-Kennzahlen:
 * - Mietrendite
 * - ROI
 * - Wertentwicklung
 * - Leerstandsquote
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary für graceful degradation
 * - Konsistente Fehlerbehandlung
 * - Real-time Updates via WebSocket
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
    Home,
    TrendingUp,
    TrendingDown,
    ChevronRight,
    AlertTriangle,
    Percent,
    Building2,
    Euro,
    Users,
} from 'lucide-react';

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';

// Types
interface PropertyKPI {
    property_count: number;
    total_value: number;
    rental_yield: number;
    roi: number;
    value_change_percent: number;
    vacancy_rate: number;
    monthly_income: number;
    monthly_expenses: number;
    net_operating_income: number;
    currency: string;
}

interface PropertySummary {
    id: string;
    name: string;
    type: string;
    rental_yield: number;
    occupancy_rate: number;
    status: 'healthy' | 'warning' | 'critical';
}

interface PropertyKPIsResponse {
    kpis: PropertyKPI;
    top_properties: PropertySummary[];
    last_updated: string;
}

// API Hook
function usePropertyKPIs() {
    return useQuery({
        queryKey: ['properties', 'kpis'],
        queryFn: async (): Promise<PropertyKPIsResponse> => {
            const response = await api.get('/api/v1/properties/kpis');
            return response.data;
        },
        staleTime: 5 * 60 * 1000,
        refetchInterval: 5 * 60 * 1000,
    });
}

// Helper functions
const formatCurrency = (value: number, currency: string = 'EUR'): string => {
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency,
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(value);
};

const formatPercent = (value: number, showSign: boolean = false): string => {
    const sign = showSign && value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(1)}%`;
};

const getStatusColor = (status: string): string => {
    switch (status) {
        case 'healthy':
            return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200';
        case 'warning':
            return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200';
        case 'critical':
            return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200';
        default:
            return 'bg-gray-100 text-gray-800';
    }
};

const getPropertyTypeLabel = (type: string): string => {
    const labels: Record<string, string> = {
        residential: 'Wohnimmobilie',
        commercial: 'Gewerbe',
        mixed: 'Gemischt',
        land: 'Grundstück',
    };
    return labels[type] || type;
};

// Components
function KPICard({
    title,
    value,
    subtitle,
    icon: Icon,
    trend,
    trendValue,
}: {
    title: string;
    value: string;
    subtitle?: string;
    icon: typeof Home;
    trend?: 'up' | 'down' | 'neutral';
    trendValue?: string;
}) {
    return (
        <div className="p-3 rounded-lg border bg-muted/30">
            <div className="flex items-center gap-2 mb-1">
                <Icon className="h-4 w-4 text-muted-foreground" />
                <span className="text-xs font-medium text-muted-foreground">
                    {title}
                </span>
            </div>
            <div className="flex items-end justify-between">
                <p className="text-xl font-bold">{value}</p>
                {trend && trendValue && (
                    <div className={cn(
                        'flex items-center gap-0.5 text-xs font-medium',
                        trend === 'up' ? 'text-green-600' :
                        trend === 'down' ? 'text-red-600' :
                        'text-muted-foreground'
                    )}>
                        {trend === 'up' ? (
                            <TrendingUp className="h-3 w-3" />
                        ) : trend === 'down' ? (
                            <TrendingDown className="h-3 w-3" />
                        ) : null}
                        {trendValue}
                    </div>
                )}
            </div>
            {subtitle && (
                <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
            )}
        </div>
    );
}

function PropertyItem({ property }: { property: PropertySummary }) {
    return (
        <div className="flex items-center justify-between py-2">
            <div className="flex items-center gap-2 min-w-0">
                <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
                <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{property.name}</p>
                    <p className="text-xs text-muted-foreground">
                        {getPropertyTypeLabel(property.type)}
                    </p>
                </div>
            </div>
            <div className="flex items-center gap-2">
                <span className="text-sm font-medium">
                    {formatPercent(property.rental_yield)}
                </span>
                <Badge
                    variant="outline"
                    className={cn('text-xs', getStatusColor(property.status))}
                >
                    {property.occupancy_rate.toFixed(0)}%
                </Badge>
            </div>
        </div>
    );
}

function PropertyKPIsWidgetContent() {
    // Real-time updates
    useWidgetSubscription('properties', {
        debounceMs: 1000,
        autoInvalidate: true,
        queryKeysToInvalidate: [['properties']],
    });

    const {
        data: response,
        isLoading,
        isError,
    } = usePropertyKPIs();

    if (isLoading) {
        return (
            <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                    {[1, 2, 3, 4].map((i) => (
                        <Skeleton key={i} className="h-20 rounded-lg" />
                    ))}
                </div>
                <Skeleton className="h-32 rounded-lg" />
            </div>
        );
    }

    if (isError || !response) {
        return (
            <div className="text-center py-6 text-muted-foreground">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
                <p className="text-sm">Immobilien-Daten nicht verfügbar</p>
            </div>
        );
    }

    const { kpis, top_properties } = response;
    const isValuePositive = kpis.value_change_percent >= 0;

    return (
        <div className="space-y-4">
            {/* KPI Grid */}
            <div className="grid grid-cols-2 gap-3">
                <KPICard
                    title="Mietrendite"
                    value={formatPercent(kpis.rental_yield)}
                    icon={Percent}
                    trend={kpis.rental_yield >= 4 ? 'up' : kpis.rental_yield < 3 ? 'down' : 'neutral'}
                    trendValue={kpis.rental_yield >= 4 ? 'Gut' : kpis.rental_yield < 3 ? 'Niedrig' : 'OK'}
                />
                <KPICard
                    title="ROI"
                    value={formatPercent(kpis.roi)}
                    icon={TrendingUp}
                    trend={kpis.roi >= 5 ? 'up' : kpis.roi < 2 ? 'down' : 'neutral'}
                    trendValue={formatPercent(kpis.value_change_percent, true)}
                />
                <KPICard
                    title="Monatl. Einnahmen"
                    value={formatCurrency(kpis.monthly_income, kpis.currency)}
                    subtitle={`Netto: ${formatCurrency(kpis.net_operating_income, kpis.currency)}`}
                    icon={Euro}
                />
                <KPICard
                    title="Leerstand"
                    value={formatPercent(kpis.vacancy_rate)}
                    icon={Users}
                    trend={kpis.vacancy_rate <= 5 ? 'up' : kpis.vacancy_rate > 10 ? 'down' : 'neutral'}
                    trendValue={kpis.vacancy_rate <= 5 ? 'Optimal' : kpis.vacancy_rate > 10 ? 'Hoch' : 'Normal'}
                />
            </div>

            {/* Property Count & Value */}
            <div className={cn(
                'p-3 rounded-lg border',
                isValuePositive
                    ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                    : 'bg-muted/30'
            )}>
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Home className="h-5 w-5 text-primary" />
                        <div>
                            <p className="text-sm font-medium">
                                {kpis.property_count} Immobilien
                            </p>
                            <p className="text-xs text-muted-foreground">
                                Gesamtwert: {formatCurrency(kpis.total_value, kpis.currency)}
                            </p>
                        </div>
                    </div>
                    <div className={cn(
                        'flex items-center gap-1',
                        isValuePositive ? 'text-green-600' : 'text-red-600'
                    )}>
                        {isValuePositive ? (
                            <TrendingUp className="h-4 w-4" />
                        ) : (
                            <TrendingDown className="h-4 w-4" />
                        )}
                        <span className="text-sm font-medium">
                            {formatPercent(kpis.value_change_percent, true)}
                        </span>
                    </div>
                </div>
            </div>

            {/* Top Properties */}
            {top_properties && top_properties.length > 0 && (
                <div className="space-y-1">
                    <p className="text-xs font-medium text-muted-foreground">
                        Top Immobilien (nach Rendite)
                    </p>
                    <div className="divide-y">
                        {top_properties.slice(0, 3).map((property) => (
                            <PropertyItem key={property.id} property={property} />
                        ))}
                    </div>
                </div>
            )}

            {/* Link to properties */}
            <Link
                to="/privat/immobilien"
                className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
                Alle Immobilien anzeigen
                <ChevronRight className="h-4 w-4" />
            </Link>
        </div>
    );
}

export function PropertyKPIsWidget() {
    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Immobilien" />}
            errorTitle="Immobilien Fehler"
            errorDescription="Die Immobilien-Daten konnten nicht geladen werden."
        >
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Home className="h-5 w-5 text-primary" />
                        Immobilien KPIs
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <PropertyKPIsWidgetContent />
                </CardContent>
            </Card>
        </ErrorBoundary>
    );
}
