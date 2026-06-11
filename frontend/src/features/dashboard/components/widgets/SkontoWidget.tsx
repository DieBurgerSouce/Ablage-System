/**
 * Skonto Widget für Dashboard
 * Zeigt Skonto-Möglichkeiten mit KPIs und dringenden Fristen
 */

import { useMemo } from 'react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError, QueryErrorAlert, KPICard } from '../shared';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Percent, Clock, TrendingDown, AlertCircle } from 'lucide-react';
import { useSkontoOpportunities } from '@/features/banking/hooks/use-banking-queries';

export function SkontoWidget() {
    const {
        data: opportunities,
        isLoading,
        isError,
        error,
        refetch
    } = useSkontoOpportunities({ days_ahead: 30 });

    // Berechne Statistiken
    const stats = useMemo(() => {
        if (!opportunities?.length) {
            return {
                total: 0,
                totalSavings: 0,
                urgent: 0,
                expiringSoon: 0,
                avgPercent: 0
            };
        }

        let totalSavings = 0;
        let urgent = 0;
        let expiringSoon = 0;
        let totalPercent = 0;
        let activeCount = 0;

        opportunities.forEach((opp) => {
            const daysRemaining = opp.skonto_days_remaining ?? 0;

            if (daysRemaining >= 0) {
                if (opp.skonto_amount) {
                    totalSavings += opp.skonto_amount;
                }
                if (opp.skonto_percent) {
                    totalPercent += opp.skonto_percent;
                    activeCount++;
                }
                if (daysRemaining <= 3) urgent++;
                if (daysRemaining <= 7) expiringSoon++;
            }
        });

        return {
            total: opportunities.filter(o => (o.skonto_days_remaining ?? 0) >= 0).length,
            totalSavings,
            urgent,
            expiringSoon,
            avgPercent: activeCount > 0 ? totalPercent / activeCount : 0
        };
    }, [opportunities]);

    const getTrend = (value: number, threshold: number): 'positive' | 'warning' | 'neutral' => {
        // Für Skonto ist es positiv, wenn es Möglichkeiten gibt
        if (value > threshold) return 'positive';
        if (value > 0) return 'neutral';
        return 'neutral';
    };

    const getUrgentTrend = (value: number): 'positive' | 'warning' | 'neutral' => {
        // Dringende Skonto-Fristen sind eine Warnung
        if (value > 3) return 'warning';
        if (value > 0) return 'warning';
        return 'positive';
    };

    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Skonto" />}
            errorTitle="Skonto Fehler"
            errorDescription="Die Skonto-Daten konnten nicht geladen werden."
        >
            <section className="space-y-4" aria-labelledby="skonto-heading">
                <h2 id="skonto-heading" className="text-xl font-semibold">Skonto-Chancen</h2>

                {/* Dringende Warnung */}
                {stats.urgent > 0 && (
                    <Alert variant="destructive" className="border-orange-500 bg-orange-50 dark:bg-orange-950">
                        <AlertCircle className="h-4 w-4 text-orange-600" />
                        <AlertDescription className="text-orange-800 dark:text-orange-200">
                            <strong>{stats.urgent} Skonto-Frist{stats.urgent > 1 ? 'en' : ''}</strong> lauf{stats.urgent > 1 ? 'en' : 't'} in den nächsten 3 Tagen ab!{' '}
                            <a href="/banking?tab=skonto" className="underline font-medium">
                                Jetzt prüfen
                            </a>
                        </AlertDescription>
                    </Alert>
                )}

                {isError ? (
                    <QueryErrorAlert
                        title="Skonto-Daten nicht verfügbar"
                        error={error as Error}
                        onRetry={() => refetch()}
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
                            title="Offene Skonto"
                            value={stats.total}
                            icon={Percent}
                            trend={getTrend(stats.total, 3)}
                            subtext={stats.total > 0 ? `${stats.avgPercent.toFixed(1)}% im Schnitt` : 'Keine Möglichkeiten'}
                            href="/banking?tab=skonto"
                            isCurrency={false}
                        />
                        <KPICard
                            title="Mögliche Ersparnis"
                            value={stats.totalSavings}
                            icon={TrendingDown}
                            trend={getTrend(stats.totalSavings, 100)}
                            subtext="nutzen und sparen"
                            href="/banking?tab=skonto"
                        />
                        <KPICard
                            title="Dringend"
                            value={stats.urgent}
                            icon={AlertCircle}
                            trend={getUrgentTrend(stats.urgent)}
                            subtext="innerhalb 3 Tagen"
                            href="/banking?tab=skonto"
                            isCurrency={false}
                        />
                        <KPICard
                            title="Diese Woche"
                            value={stats.expiringSoon}
                            icon={Clock}
                            trend={stats.expiringSoon > 0 ? 'neutral' : 'positive'}
                            subtext="ablaufende Fristen"
                            href="/banking?tab=skonto"
                            isCurrency={false}
                        />
                    </div>
                )}
            </section>
        </ErrorBoundary>
    );
}
