/**
 * Portfolio Summary Widget für Dashboard
 *
 * Zeigt Nettovermögen und Vermögensaufteilung:
 * - Gesamtvermögen nach Asset-Klassen
 * - Performance-Indikatoren
 * - Trend-Visualisierung
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary für graceful degradation
 * - Konsistente Fehlerbehandlung
 * - Real-time Updates via WebSocket
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
    PiggyBank,
    TrendingUp,
    TrendingDown,
    ChevronRight,
    AlertTriangle,
    Building2,
    Banknote,
    Landmark,
    Briefcase,
} from 'lucide-react';

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';

// Types
interface AssetAllocation {
    category: string;
    value: number;
    percentage: number;
    change_percent: number;
}

interface PortfolioSummary {
    total_value: number;
    total_change_percent: number;
    total_change_absolute: number;
    currency: string;
    allocations: AssetAllocation[];
    last_updated: string;
}

// API Hook
function usePortfolioSummary() {
    return useQuery({
        queryKey: ['portfolio', 'summary'],
        queryFn: async (): Promise<PortfolioSummary> => {
            const response = await api.get('/portfolio/summary');
            return response.data;
        },
        staleTime: 5 * 60 * 1000, // 5 minutes
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

const formatPercent = (value: number): string => {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(1)}%`;
};

const getCategoryIcon = (category: string) => {
    switch (category.toLowerCase()) {
        case 'immobilien':
        case 'real_estate':
            return Building2;
        case 'bargeld':
        case 'cash':
            return Banknote;
        case 'aktien':
        case 'stocks':
            return TrendingUp;
        case 'anleihen':
        case 'bonds':
            return Landmark;
        default:
            return Briefcase;
    }
};

const getCategoryLabel = (category: string): string => {
    const labels: Record<string, string> = {
        real_estate: 'Immobilien',
        immobilien: 'Immobilien',
        cash: 'Bargeld',
        bargeld: 'Bargeld',
        stocks: 'Aktien',
        aktien: 'Aktien',
        bonds: 'Anleihen',
        anleihen: 'Anleihen',
        other: 'Sonstiges',
        sonstiges: 'Sonstiges',
    };
    return labels[category.toLowerCase()] || category;
};

const getCategoryColor = (index: number): string => {
    const colors = [
        'bg-blue-500',
        'bg-green-500',
        'bg-purple-500',
        'bg-orange-500',
        'bg-pink-500',
    ];
    return colors[index % colors.length];
};

// Components
function AllocationBar({ allocations }: { allocations: AssetAllocation[] }) {
    return (
        <div className="flex h-3 rounded-full overflow-hidden bg-muted">
            {allocations.map((alloc, index) => (
                <div
                    key={alloc.category}
                    className={cn(getCategoryColor(index), 'transition-all')}
                    style={{ width: `${alloc.percentage}%` }}
                    title={`${getCategoryLabel(alloc.category)}: ${alloc.percentage.toFixed(1)}%`}
                />
            ))}
        </div>
    );
}

function AllocationItem({ allocation, index }: { allocation: AssetAllocation; index: number }) {
    const Icon = getCategoryIcon(allocation.category);
    const isPositive = allocation.change_percent >= 0;

    return (
        <div className="flex items-center justify-between py-2">
            <div className="flex items-center gap-2">
                <div className={cn('w-3 h-3 rounded-full', getCategoryColor(index))} />
                <Icon className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">
                    {getCategoryLabel(allocation.category)}
                </span>
            </div>
            <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">
                    {allocation.percentage.toFixed(0)}%
                </span>
                <span className={cn(
                    'text-xs font-medium',
                    isPositive ? 'text-green-600' : 'text-red-600'
                )}>
                    {formatPercent(allocation.change_percent)}
                </span>
            </div>
        </div>
    );
}

function PortfolioSummaryWidgetContent() {
    // Real-time updates
    useWidgetSubscription('portfolio', {
        debounceMs: 1000,
        autoInvalidate: true,
        queryKeysToInvalidate: [['portfolio']],
    });

    const {
        data: summary,
        isLoading,
        isError,
    } = usePortfolioSummary();

    if (isLoading) {
        return (
            <div className="space-y-4">
                <Skeleton className="h-16 rounded-lg" />
                <Skeleton className="h-3 rounded-full" />
                <div className="space-y-2">
                    {[1, 2, 3, 4].map((i) => (
                        <Skeleton key={i} className="h-10 rounded-lg" />
                    ))}
                </div>
            </div>
        );
    }

    if (isError || !summary) {
        return (
            <div className="text-center py-6 text-muted-foreground">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
                <p className="text-sm">Portfolio-Daten nicht verfügbar</p>
            </div>
        );
    }

    const isPositive = summary.total_change_percent >= 0;
    const TrendIcon = isPositive ? TrendingUp : TrendingDown;

    return (
        <div className="space-y-4">
            {/* Total Value */}
            <div className={cn(
                'p-4 rounded-lg border',
                isPositive
                    ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                    : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
            )}>
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs font-medium text-muted-foreground">
                            Gesamtvermögen
                        </p>
                        <p className="text-2xl font-bold">
                            {formatCurrency(summary.total_value, summary.currency)}
                        </p>
                    </div>
                    <div className={cn(
                        'flex items-center gap-1 px-2 py-1 rounded',
                        isPositive
                            ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300'
                            : 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300'
                    )}>
                        <TrendIcon className="h-4 w-4" />
                        <span className="text-sm font-medium">
                            {formatPercent(summary.total_change_percent)}
                        </span>
                    </div>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                    {isPositive ? '+' : ''}{formatCurrency(summary.total_change_absolute, summary.currency)} diesen Monat
                </p>
            </div>

            {/* Allocation Bar */}
            <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">
                    Vermögensaufteilung
                </p>
                <AllocationBar allocations={summary.allocations} />
            </div>

            {/* Allocation Details */}
            <div className="divide-y">
                {summary.allocations.slice(0, 4).map((allocation, index) => (
                    <AllocationItem
                        key={allocation.category}
                        allocation={allocation}
                        index={index}
                    />
                ))}
            </div>

            {/* Link to full portfolio */}
            <Link
                to="/privat/portfolio"
                className="flex items-center justify-center gap-2 text-sm text-primary hover:underline"
            >
                Portfolio-Details anzeigen
                <ChevronRight className="h-4 w-4" />
            </Link>
        </div>
    );
}

export function PortfolioSummaryWidget() {
    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Portfolio" />}
            errorTitle="Portfolio Fehler"
            errorDescription="Die Portfolio-Daten konnten nicht geladen werden."
        >
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <PiggyBank className="h-5 w-5 text-primary" />
                        Portfolio Übersicht
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <PortfolioSummaryWidgetContent />
                </CardContent>
            </Card>
        </ErrorBoundary>
    );
}
