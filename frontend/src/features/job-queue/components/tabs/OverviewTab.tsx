/**
 * Overview Tab
 *
 * KPI Cards und Mini-Charts für schnellen Überblick.
 */

import { useMemo } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Cpu,
  Flame,
  Gauge,
  TrendingUp,
  XCircle,
  Zap,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';

import { useJobStats, useWorkersList, useDLQStats, useQueuesList } from '../../hooks/use-jobs-query';
import { JOB_TYPE_CONFIG } from '../../types/job-types';
import { JobThroughputChart, SuccessRateChart, QueueLengthChart } from '../charts';
import { DASHBOARD_KPI_THRESHOLDS, SUCCESS_RATE_THRESHOLDS } from '../../constants/thresholds';

// ==================== KPI Card Component ====================

interface KPICardProps {
  title: string;
  value: string | number;
  description?: string;
  icon: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  status?: 'success' | 'warning' | 'error' | 'default';
  isLoading?: boolean;
}

function KPICard({
  title,
  value,
  description,
  icon,
  trend,
  trendValue,
  status = 'default',
  isLoading,
}: KPICardProps) {
  const statusColors = {
    success: 'text-green-600',
    warning: 'text-yellow-600',
    error: 'text-red-600',
    default: 'text-foreground',
  };

  const statusBg = {
    success: 'bg-green-50 dark:bg-green-950',
    warning: 'bg-yellow-50 dark:bg-yellow-950',
    error: 'bg-red-50 dark:bg-red-950',
    default: 'bg-muted',
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <div className={`p-2 rounded-lg ${statusBg[status]}`}>{icon}</div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-8 w-20" />
        ) : (
          <>
            <div className={`text-2xl font-bold ${statusColors[status]}`}>{value}</div>
            {description && (
              <p className="text-xs text-muted-foreground mt-1">{description}</p>
            )}
            {trend && trendValue && (
              <div className="flex items-center gap-1 mt-2">
                {trend === 'up' && <TrendingUp className="h-3 w-3 text-green-600" />}
                {trend === 'down' && <TrendingUp className="h-3 w-3 text-red-600 rotate-180" />}
                <span
                  className={`text-xs ${
                    trend === 'up' ? 'text-green-600' : trend === 'down' ? 'text-red-600' : ''
                  }`}
                >
                  {trendValue}
                </span>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ==================== Main Component ====================

export function OverviewTab() {
  const { data: stats, isLoading: statsLoading } = useJobStats();
  const { data: workers, isLoading: workersLoading } = useWorkersList();
  const { data: dlqStats } = useDLQStats();
  const { data: queues, isLoading: queuesLoading } = useQueuesList();

  // Berechne abgeleitete Werte
  const successRateStatus = useMemo(() => {
    if (!stats?.successRate24h) return 'default';
    if (stats.successRate24h >= SUCCESS_RATE_THRESHOLDS.EXCELLENT) return 'success';
    if (stats.successRate24h >= SUCCESS_RATE_THRESHOLDS.GOOD) return 'warning';
    return 'error';
  }, [stats?.successRate24h]);

  const gpuMemoryPercent = workers?.gpu?.memoryPercent ?? 0;
  const gpuStatus = useMemo(() => {
    if (gpuMemoryPercent >= 85) return 'error';
    if (gpuMemoryPercent >= 70) return 'warning';
    return 'success';
  }, [gpuMemoryPercent]);

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}min`;
  };

  return (
    <div className="space-y-6">
      {/* Haupt-KPIs */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title="Aktive Jobs"
          value={stats?.activeJobs ?? 0}
          description={`${stats?.queuedJobs ?? 0} in Warteschlange`}
          icon={<Zap className="h-4 w-4 text-yellow-600" />}
          status={
            (stats?.activeJobs ?? 0) > 50
              ? 'warning'
              : (stats?.activeJobs ?? 0) > 0
                ? 'default'
                : 'success'
          }
          isLoading={statsLoading}
        />

        <KPICard
          title="Erfolgsrate (24h)"
          value={`${stats?.successRate24h?.toFixed(1) ?? 0}%`}
          description={`${stats?.completed24h ?? 0} abgeschlossen`}
          icon={<CheckCircle2 className="h-4 w-4 text-green-600" />}
          status={successRateStatus}
          isLoading={statsLoading}
        />

        <KPICard
          title="Durchsatz/Stunde"
          value={stats?.throughputPerHour?.toFixed(0) ?? 0}
          description="Jobs pro Stunde"
          icon={<Gauge className="h-4 w-4 text-blue-600" />}
          isLoading={statsLoading}
        />

        <KPICard
          title="Fehlgeschlagen (24h)"
          value={stats?.failed24h ?? 0}
          description={dlqStats?.totalTasks ? `${dlqStats.totalTasks} in DLQ` : 'DLQ leer'}
          icon={<XCircle className="h-4 w-4 text-red-600" />}
          status={(stats?.failed24h ?? 0) > DASHBOARD_KPI_THRESHOLDS.FAILED_JOBS_ERROR ? 'error' : 'default'}
          isLoading={statsLoading}
        />
      </div>

      {/* Sekundaere KPIs */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title="Durchschn. Verarbeitungszeit"
          value={stats?.avgProcessingTimeMs ? formatDuration(stats.avgProcessingTimeMs) : '-'}
          icon={<Clock className="h-4 w-4 text-purple-600" />}
          isLoading={statsLoading}
        />

        <KPICard
          title="Durchschn. Wartezeit"
          value={stats?.avgWaitTimeMs ? formatDuration(stats.avgWaitTimeMs) : '-'}
          icon={<Clock className="h-4 w-4 text-orange-600" />}
          isLoading={statsLoading}
        />

        <KPICard
          title="Online Worker"
          value={`${workers?.onlineWorkers ?? 0} / ${workers?.totalWorkers ?? 0}`}
          description={workers?.busyWorkers ? `${workers.busyWorkers} beschäftigt` : undefined}
          icon={<Cpu className="h-4 w-4 text-indigo-600" />}
          status={(workers?.onlineWorkers ?? 0) === 0 ? 'error' : 'success'}
          isLoading={workersLoading}
        />

        <KPICard
          title="GPU Auslastung"
          value={workers?.gpu?.available ? `${gpuMemoryPercent.toFixed(0)}%` : 'N/A'}
          description={
            workers?.gpu?.available
              ? `${workers.gpu.memoryUsedMb?.toFixed(0) ?? 0} / ${workers.gpu.memoryTotalMb?.toFixed(0) ?? 0} MB`
              : 'Nicht verfügbar'
          }
          icon={<Flame className="h-4 w-4 text-red-600" />}
          status={workers?.gpu?.available ? gpuStatus : 'default'}
          isLoading={workersLoading}
        />
      </div>

      {/* Jobs nach Typ und Backend */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Jobs nach Typ */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Jobs nach Typ (24h)</CardTitle>
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="space-y-2">
                {[1, 2, 3, 4].map((i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {Object.entries(stats?.jobsByType ?? {}).map(([type, count]) => {
                  const config = JOB_TYPE_CONFIG[type as keyof typeof JOB_TYPE_CONFIG];
                  const total = stats?.jobs24h ?? 1;
                  const percent = ((count as number) / total) * 100;

                  return (
                    <div key={type} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-2">
                          <Badge variant="outline">{config?.label ?? type}</Badge>
                        </span>
                        <span className="font-medium">{count as number}</span>
                      </div>
                      <Progress value={percent} className="h-2" />
                    </div>
                  );
                })}
                {Object.keys(stats?.jobsByType ?? {}).length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    Keine Jobs in den letzten 24 Stunden
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Jobs nach Backend */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Jobs nach Backend (24h)</CardTitle>
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-6 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {Object.entries(stats?.jobsByBackend ?? {}).map(([backend, count]) => {
                  const total = stats?.jobs24h ?? 1;
                  const percent = ((count as number) / total) * 100;

                  return (
                    <div key={backend} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-2">
                          <Badge variant="secondary">{backend}</Badge>
                        </span>
                        <span className="font-medium">{count as number}</span>
                      </div>
                      <Progress value={percent} className="h-2" />
                    </div>
                  );
                })}
                {Object.keys(stats?.jobsByBackend ?? {}).length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    Keine Backend-Daten verfügbar
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Queue Übersicht */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Queue Status</CardTitle>
          <CardDescription>Übersicht aller Warteschlangen</CardDescription>
        </CardHeader>
        <CardContent>
          {queuesLoading ? (
            <div className="grid gap-4 md:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-3">
              {queues?.queues?.map((queue) => (
                <div
                  key={queue.name}
                  className="flex items-center justify-between p-4 border rounded-lg"
                >
                  <div>
                    <div className="font-medium">{queue.name}</div>
                    <div className="text-sm text-muted-foreground">{queue.description}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold">{queue.length}</div>
                    <div className="text-xs text-muted-foreground">
                      {queue.processing} aktiv
                    </div>
                  </div>
                </div>
              ))}
              {(!queues?.queues || queues.queues.length === 0) && (
                <p className="text-sm text-muted-foreground col-span-3 text-center py-4">
                  Keine Queues verfügbar
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Performance Charts
          Hinweis: useJobStats liefert nur 24h-Aggregate (successRate24h,
          throughputPerHour, ...), aber KEINEN stündlichen 24h-Verlauf.
          Bis ein Verlaufs-Endpoint existiert, bleiben diese Charts bewusst
          ohne Daten (ehrlicher Empty-State) statt Mock-/Zufallsdaten.
          Folgepunkt (G1): stündlichen 24h-Verlaufs-Endpoint bereitstellen
          und hier als data-Prop durchreichen. */}
      <div className="grid gap-4 lg:grid-cols-2">
        <JobThroughputChart isLoading={statsLoading} />
        <SuccessRateChart isLoading={statsLoading} />
      </div>

      {/* Queue Length Chart */}
      <QueueLengthChart
        data={queues?.queues?.map((q) => ({
          name: q.name,
          displayName: q.name.charAt(0).toUpperCase() + q.name.slice(1),
          length: q.length,
          processing: q.processing,
          maxCapacity: q.maxCapacity,
        }))}
        isLoading={queuesLoading}
      />

      {/* DLQ Warnung wenn vorhanden */}
      {dlqStats && dlqStats.totalTasks > 0 && (
        <Card className="border-yellow-500/50 bg-yellow-50/50 dark:bg-yellow-950/20">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2 text-yellow-700 dark:text-yellow-500">
              <AlertTriangle className="h-4 w-4" />
              Dead Letter Queue Warnung
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-yellow-700 dark:text-yellow-500">
              {dlqStats.statusMessage}
            </p>
            {dlqStats.poisonPills > 0 && (
              <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                {dlqStats.poisonPills} Poison Pills erkannt - möglicherweise systematische Fehler
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default OverviewTab;
