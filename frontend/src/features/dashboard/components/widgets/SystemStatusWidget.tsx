import { useQuery } from '@tanstack/react-query'
import { adminService } from '@/lib/api/services/admin'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { DashboardSectionError, QueryErrorAlert, KPICard } from '../shared'
import { Skeleton } from '@/components/ui/skeleton'
import { CheckCircle, FileText, Server, Zap } from 'lucide-react'

export function SystemStatusWidget() {
    const {
        data: systemDashboard,
        isLoading: isLoadingSystem,
        isError: isSystemError,
        error: systemError,
        refetch: refetchSystem
    } = useQuery({
        queryKey: ['admin-system-dashboard'],
        queryFn: () => adminService.getSystemDashboard(),
        staleTime: 30000,
        retry: 1,
    })

    const stats = systemDashboard?.processing
    const queue = systemDashboard?.queue
    const health = systemDashboard?.health

    const getSuccessRateTrend = (rate: number | undefined): 'positive' | 'warning' | 'neutral' => {
        if (rate === undefined) return 'neutral'
        if (rate >= 90) return 'positive'
        if (rate >= 70) return 'neutral'
        return 'warning'
    }

    const getHealthSubtext = (status: string | undefined): string => {
        switch (status) {
            case 'healthy':
                return 'Alle Systeme operativ'
            case 'degraded':
                return 'Eingeschränkte Leistung'
            case 'unhealthy':
                return 'Systemprobleme erkannt'
            default:
                return 'Status unbekannt'
        }
    }

    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="System-Status" />}
            errorTitle="System-Status Fehler"
            errorDescription="Die Systemstatistiken konnten nicht geladen werden."
        >
            <section className="space-y-4" aria-labelledby="system-status-heading">
                <h2 id="system-status-heading" className="text-xl font-semibold">System-Status</h2>
                {isSystemError ? (
                    <QueryErrorAlert
                        title="Systemstatus nicht verfügbar"
                        error={systemError as Error}
                        onRetry={() => refetchSystem()}
                    />
                ) : isLoadingSystem ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        {[1, 2, 3, 4].map((i) => (
                            <Skeleton key={i} className="h-32 rounded-xl" />
                        ))}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <KPICard
                            title="Dokumente gesamt"
                            value={stats?.total_documents ?? 0}
                            icon={FileText}
                            trend="neutral"
                            subtext={`${stats?.documents_processed_today ?? 0} heute verarbeitet`}
                            href="/search"
                            isCurrency={false}
                        />
                        <KPICard
                            title="Erfolgsrate"
                            value={stats?.success_rate ?? 0}
                            icon={CheckCircle}
                            trend={getSuccessRateTrend(stats?.success_rate)}
                            subtext="OCR-Verarbeitung"
                            href="/admin"
                            isCurrency={false}
                            isPercent={true}
                        />
                        <KPICard
                            title="In Warteschlange"
                            value={(queue?.pending ?? 0) + (queue?.queued ?? 0) + (queue?.processing ?? 0)}
                            icon={Zap}
                            trend={(queue?.pending ?? 0) > 10 ? 'warning' : 'positive'}
                            subtext={`${queue?.processing ?? 0} in Bearbeitung`}
                            href="/admin/jobs"
                            isCurrency={false}
                        />
                        <KPICard
                            title="System-Status"
                            value={health?.overall_status === 'healthy' ? 100 : health?.overall_status === 'degraded' ? 50 : 0}
                            icon={Server}
                            trend={health?.overall_status === 'healthy' ? 'positive' : health?.overall_status === 'degraded' ? 'warning' : 'warning'}
                            subtext={getHealthSubtext(health?.overall_status)}
                            href="/admin"
                            isCurrency={false}
                            isPercent={true}
                        />
                    </div>
                )}
            </section>
        </ErrorBoundary>
    )
}
