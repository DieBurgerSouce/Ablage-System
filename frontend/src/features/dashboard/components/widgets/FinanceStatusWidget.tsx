import { useQuery } from '@tanstack/react-query'
import { financeService, financeAnomalyApi } from '@/lib/api/services/finance'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { DashboardSectionError, QueryErrorAlert, KPICard } from '../shared'
import { Skeleton } from '@/components/ui/skeleton'
import { AlertTriangle, Banknote, TrendingDown, TrendingUp, ShieldAlert } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Link } from '@tanstack/react-router'

export function FinanceStatusWidget() {
    const {
        data: financeAggregations,
        isLoading: isLoadingFinance,
        isError: isFinanceError,
        error: financeError,
        refetch: refetchFinance
    } = useQuery({
        queryKey: ['finance-aggregations'],
        queryFn: () => financeService.getOverallAggregations(),
        staleTime: 60000,
        retry: 1,
    })

    const {
        data: deadlines,
        isLoading: isLoadingDeadlines,
    } = useQuery({
        queryKey: ['finance-deadlines', { daysAhead: 3 }],
        queryFn: () => financeService.getDeadlines({ daysAhead: 3 }),
        staleTime: 60000,
        retry: 1,
    })

    // Anomaly Dashboard Query (Enterprise Feature)
    const {
        data: anomalyDashboard,
        isLoading: isLoadingAnomalies,
    } = useQuery({
        queryKey: ['finance-anomalies-dashboard', { limit: 5 }],
        queryFn: () => financeAnomalyApi.getDashboard({ limit: 5 }),
        staleTime: 60000,
        retry: 1,
    })

    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Finanzen" />}
            errorTitle="Finanz-Übersicht Fehler"
            errorDescription="Die Finanzdaten konnten nicht geladen werden."
        >
            <section className="space-y-4" aria-labelledby="finance-heading">
                <h2 id="finance-heading" className="text-xl font-semibold">Finanzen im Blick</h2>
                {isFinanceError ? (
                    <QueryErrorAlert
                        title="Finanzdaten nicht verfügbar"
                        error={financeError as Error}
                        onRetry={() => refetchFinance()}
                    />
                ) : isLoadingFinance || isLoadingDeadlines ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        {[1, 2, 3, 4].map((i) => (
                            <Skeleton key={i} className="h-32 rounded-xl" />
                        ))}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <KPICard
                            title="Nachzahlung gesamt"
                            value={financeAggregations?.totalNachzahlung ?? 0}
                            icon={TrendingDown}
                            trend="warning"
                            subtext="zu zahlende Beträge"
                            href="/finanzen"
                        />
                        <KPICard
                            title="Erstattung gesamt"
                            value={financeAggregations?.totalErstattung ?? 0}
                            icon={TrendingUp}
                            trend="positive"
                            subtext="erwartete Rückzahlungen"
                            href="/finanzen"
                        />
                        <KPICard
                            title="Saldo"
                            value={financeAggregations?.saldo ?? 0}
                            icon={Banknote}
                            trend={(financeAggregations?.saldo ?? 0) >= 0 ? 'positive' : 'warning'}
                            subtext="Erstattung - Nachzahlung"
                            href="/finanzen"
                        />
                        <KPICard
                            title="Offene Fristen"
                            value={deadlines?.urgentCount ?? financeAggregations?.pendingDeadlines ?? 0}
                            icon={AlertTriangle}
                            trend={(deadlines?.overdueCount ?? 0) > 0 ? 'warning' : 'neutral'}
                            subtext={`${deadlines?.overdueCount ?? 0} überfällig`}
                            href="/finanzen"
                            isCurrency={false}
                        />
                    </div>
                )}

                {/* Anomaly Alert Section (Enterprise Feature) */}
                {!isLoadingAnomalies && anomalyDashboard && anomalyDashboard.stats.suspiciousDocuments > 0 && (
                    <Card className="mt-4 border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20">
                        <CardHeader className="pb-2">
                            <CardTitle className="flex items-center gap-2 text-amber-700 dark:text-amber-400 text-base">
                                <ShieldAlert className="w-5 h-5" />
                                Anomalie-Warnung
                                <Badge
                                    variant="destructive"
                                    className="ml-auto bg-amber-600 hover:bg-amber-700"
                                >
                                    {anomalyDashboard.stats.suspiciousDocuments} verdächtig
                                </Badge>
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pt-0">
                            <p className="text-sm text-amber-600 dark:text-amber-500 mb-3">
                                {anomalyDashboard.stats.pendingReview} Dokumente zur Prüfung ausstehend
                            </p>
                            {anomalyDashboard.recentAnomalies.length > 0 && (
                                <div className="space-y-2">
                                    {anomalyDashboard.recentAnomalies.slice(0, 3).map((anomaly) => (
                                        <div
                                            key={anomaly.documentId}
                                            className="flex items-center justify-between text-sm p-2 rounded bg-white dark:bg-gray-900 border border-amber-200 dark:border-amber-800"
                                        >
                                            <div className="flex items-center gap-2 min-w-0">
                                                <span
                                                    className={`w-2 h-2 rounded-full flex-shrink-0 ${
                                                        anomaly.riskScore > 0.7 ? 'bg-red-500' :
                                                        anomaly.riskScore > 0.4 ? 'bg-amber-500' : 'bg-yellow-500'
                                                    }`}
                                                />
                                                <span className="truncate font-medium">{anomaly.documentName}</span>
                                            </div>
                                            <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                                                <Badge variant="outline" className="text-xs">
                                                    {Math.round(anomaly.riskScore * 100)}% Risiko
                                                </Badge>
                                                <Badge variant="secondary" className="text-xs">
                                                    {anomaly.anomalyCount} Anomalien
                                                </Badge>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                            <Link
                                to="/finanzen"
                                className="mt-3 block text-sm text-amber-700 dark:text-amber-400 hover:underline"
                            >
                                Alle Anomalien anzeigen
                            </Link>
                        </CardContent>
                    </Card>
                )}
            </section>
        </ErrorBoundary>
    )
}
