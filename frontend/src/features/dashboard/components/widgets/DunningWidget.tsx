/**
 * Dunning Widget für Dashboard
 * Zeigt offene Mahnungen mit KPIs
 */

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError, QueryErrorAlert, KPICard } from '../shared';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertTriangle, Clock, Receipt, Users } from 'lucide-react';
import { useDunningStats, useOverdueInvoices } from '@/features/banking/hooks/use-banking-queries';

export function DunningWidget() {
    const {
        data: dunningStats,
        isLoading: isLoadingStats,
        isError: isStatsError,
        error: statsError,
        refetch: refetchStats
    } = useDunningStats();

    const {
        data: overdueInvoices,
        isLoading: isLoadingOverdue,
    } = useOverdueInvoices();

    const isLoading = isLoadingStats || isLoadingOverdue;

    // Berechne Statistiken
    const totalOverdue = dunningStats?.total_overdue ?? 0;
    const totalAmount = dunningStats?.total_amount ?? 0;
    const oldestOverdueDays = dunningStats?.oldest_overdue_days ?? 0;
    const uniqueDebtors = overdueInvoices?.length ?? 0;

    // Mahnstufen-Verteilung
    const byLevel = dunningStats?.by_level ?? [];
    const level1Count = byLevel.find(l => l.level === '1')?.count ?? 0;
    const level2Count = byLevel.find(l => l.level === '2')?.count ?? 0;
    const level3Count = byLevel.find(l => l.level === '3')?.count ?? 0;

    const getLevelSubtext = () => {
        const parts = [];
        if (level1Count > 0) parts.push(`${level1Count} Stufe 1`);
        if (level2Count > 0) parts.push(`${level2Count} Stufe 2`);
        if (level3Count > 0) parts.push(`${level3Count} Stufe 3`);
        return parts.length > 0 ? parts.join(', ') : 'Keine Mahnungen';
    };

    const getTrend = (value: number, threshold: number): 'positive' | 'warning' | 'neutral' => {
        if (value === 0) return 'positive';
        if (value > threshold) return 'warning';
        return 'neutral';
    };

    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Mahnungen" />}
            errorTitle="Mahnungen Fehler"
            errorDescription="Die Mahndaten konnten nicht geladen werden."
        >
            <section className="space-y-4" aria-labelledby="dunning-heading">
                <h2 id="dunning-heading" className="text-xl font-semibold">Offene Mahnungen</h2>
                {isStatsError ? (
                    <QueryErrorAlert
                        title="Mahndaten nicht verfügbar"
                        error={statsError as Error}
                        onRetry={() => refetchStats()}
                    />
                ) : isLoading ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        {[1, 2, 3, 4].map((i) => (
                            <Skeleton key={i} className="h-32 rounded-xl" />
                        ))}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <KPICard
                            title="Offene Posten"
                            value={totalOverdue}
                            icon={Receipt}
                            trend={getTrend(totalOverdue, 10)}
                            subtext={getLevelSubtext()}
                            href="/banking?tab=dunning"
                            isCurrency={false}
                        />
                        <KPICard
                            title="Gesamtbetrag"
                            value={totalAmount}
                            icon={AlertTriangle}
                            trend={getTrend(totalAmount, 10000)}
                            subtext="ausstehend"
                            href="/banking?tab=dunning"
                        />
                        <KPICard
                            title="Älteste Mahnung"
                            value={oldestOverdueDays}
                            icon={Clock}
                            trend={getTrend(oldestOverdueDays, 60)}
                            subtext="Tage überfällig"
                            href="/banking?tab=dunning"
                            isCurrency={false}
                        />
                        <KPICard
                            title="Betroffene Kunden"
                            value={uniqueDebtors}
                            icon={Users}
                            trend={getTrend(uniqueDebtors, 5)}
                            subtext="mit offenen Posten"
                            href="/banking?tab=dunning"
                            isCurrency={false}
                        />
                    </div>
                )}
            </section>
        </ErrorBoundary>
    );
}
