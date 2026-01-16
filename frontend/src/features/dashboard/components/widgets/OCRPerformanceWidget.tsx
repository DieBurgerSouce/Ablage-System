/**
 * OCR Performance Widget für Dashboard
 * Zeigt OCR-Metriken: Erfolgsrate, Durchsatz, Backend-Verteilung
 */

import { useQuery } from '@tanstack/react-query';
import { adminService } from '@/lib/api/services/admin';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError, QueryErrorAlert, KPICard } from '../shared';
import { Skeleton } from '@/components/ui/skeleton';
import { CheckCircle, Clock, FileText, Zap } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

export function OCRPerformanceWidget() {
    const {
        data: systemDashboard,
        isLoading,
        isError,
        error,
        refetch
    } = useQuery({
        queryKey: ['admin-system-dashboard'],
        queryFn: () => adminService.getSystemDashboard(),
        staleTime: 30000,
        retry: 1,
    });

    const processing = systemDashboard?.processing;
    const queue = systemDashboard?.queue;

    const getSuccessRateTrend = (rate: number | undefined): 'positive' | 'warning' | 'neutral' => {
        if (rate === undefined) return 'neutral';
        if (rate >= 95) return 'positive';
        if (rate >= 85) return 'neutral';
        return 'warning';
    };

    // Backend-Verteilung berechnen
    const backends = processing?.by_backend ?? {};
    const backendEntries = Object.entries(backends).map(([name, stats]) => ({
        name,
        count: stats.count,
        successRate: stats.success_rate,
        avgTimeMs: stats.avg_time_ms,
    }));
    const totalBackendCount = backendEntries.reduce((sum, b) => sum + b.count, 0);

    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="OCR-Performance" />}
            errorTitle="OCR-Performance Fehler"
            errorDescription="Die OCR-Metriken konnten nicht geladen werden."
        >
            <section className="space-y-4" aria-labelledby="ocr-heading">
                <h2 id="ocr-heading" className="text-xl font-semibold">OCR-Performance</h2>
                {isError ? (
                    <QueryErrorAlert
                        title="OCR-Metriken nicht verfügbar"
                        error={error as Error}
                        onRetry={() => refetch()}
                    />
                ) : isLoading ? (
                    <div className="space-y-4">
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                            {[1, 2, 3, 4].map((i) => (
                                <Skeleton key={i} className="h-32 rounded-xl" />
                            ))}
                        </div>
                        <Skeleton className="h-24 rounded-xl" />
                    </div>
                ) : (
                    <>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                            <KPICard
                                title="Erfolgsrate"
                                value={processing?.success_rate ?? 0}
                                icon={CheckCircle}
                                trend={getSuccessRateTrend(processing?.success_rate)}
                                subtext="OCR-Verarbeitung"
                                href="/admin"
                                isCurrency={false}
                                isPercent={true}
                            />
                            <KPICard
                                title="Heute verarbeitet"
                                value={processing?.documents_processed_today ?? 0}
                                icon={FileText}
                                trend="neutral"
                                subtext={`${processing?.documents_processed_hour ?? 0} in der letzten Stunde`}
                                href="/admin"
                                isCurrency={false}
                            />
                            <KPICard
                                title="Ø Verarbeitungszeit"
                                value={Math.round((processing?.avg_processing_time_ms ?? 0) / 1000)}
                                icon={Clock}
                                trend={(processing?.avg_processing_time_ms ?? 0) < 5000 ? 'positive' : 'warning'}
                                subtext="Sekunden pro Dokument"
                                href="/admin"
                                isCurrency={false}
                            />
                            <KPICard
                                title="In Warteschlange"
                                value={(queue?.pending ?? 0) + (queue?.queued ?? 0)}
                                icon={Zap}
                                trend={(queue?.pending ?? 0) > 10 ? 'warning' : 'positive'}
                                subtext={`${queue?.processing ?? 0} in Bearbeitung`}
                                href="/admin/jobs"
                                isCurrency={false}
                            />
                        </div>

                        {/* Backend-Verteilung */}
                        {backendEntries.length > 0 && totalBackendCount > 0 && (
                            <Card>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm font-medium">Backend-Verteilung (heute)</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    {backendEntries.map((backend) => {
                                        const percentage = totalBackendCount > 0
                                            ? Math.round((backend.count / totalBackendCount) * 100)
                                            : 0;
                                        return (
                                            <div key={backend.name} className="space-y-1">
                                                <div className="flex justify-between text-sm">
                                                    <span className="font-medium">{backend.name}</span>
                                                    <span className="text-muted-foreground">
                                                        {backend.count} ({percentage}%) · {Math.round(backend.successRate)}% Erfolg
                                                    </span>
                                                </div>
                                                <Progress value={percentage} className="h-2" />
                                            </div>
                                        );
                                    })}
                                </CardContent>
                            </Card>
                        )}
                    </>
                )}
            </section>
        </ErrorBoundary>
    );
}
