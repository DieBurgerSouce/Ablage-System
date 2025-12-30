import { useQuery } from '@tanstack/react-query'
import { financeService } from '@/lib/api/services/finance'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { DashboardSectionError, QueryErrorAlert, KPICard } from '../shared'
import { Skeleton } from '@/components/ui/skeleton'
import { AlertTriangle, Banknote, TrendingDown, TrendingUp } from 'lucide-react'

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
            </section>
        </ErrorBoundary>
    )
}
