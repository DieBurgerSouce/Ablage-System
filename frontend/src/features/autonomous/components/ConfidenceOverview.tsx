/**
 * Confidence Overview Component
 * Displays statistics and metrics about autonomous system performance
 */

import { TrendingUp, Activity, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { useProposalStatistics, useTrustMetrics } from '../hooks/useAutonomous';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  progressValue?: number;
  progressLabel?: string;
}

function StatCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  progressValue,
  progressLabel,
}: StatCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
        {progressValue !== undefined && (
          <div className="mt-3 space-y-1">
            <Progress value={progressValue} className="h-2" />
            {progressLabel && (
              <p className="text-xs text-muted-foreground">{progressLabel}</p>
            )}
          </div>
        )}
        {trend && (
          <div
            className={cn(
              'flex items-center gap-1 text-xs mt-2',
              trend === 'up' && 'text-green-600',
              trend === 'down' && 'text-red-600',
              trend === 'neutral' && 'text-muted-foreground'
            )}
          >
            <TrendingUp className="h-3 w-3" />
            {trend === 'up' && 'Steigend'}
            {trend === 'down' && 'Fallend'}
            {trend === 'neutral' && 'Stabil'}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function ConfidenceOverview() {
  const { data: statistics, isLoading: statsLoading } = useProposalStatistics(30);
  const { data: metrics, isLoading: metricsLoading } = useTrustMetrics(30);

  if (statsLoading || metricsLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardHeader>
              <CardTitle className="text-sm">Lädt...</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-8 bg-muted rounded animate-pulse"></div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!statistics || !metrics) {
    return null;
  }

  const totalDecisions = statistics.total_proposals;
  const avgConfidence = Math.round((statistics.avg_confidence || 0) * 100);
  const autoAcceptanceRate = Math.round((statistics.auto_acceptance_rate || 0) * 100);
  const approvalRate = Math.round((statistics.approval_rate || 0) * 100);
  const rejectionRate = Math.round((statistics.rejection_rate || 0) * 100);
  const pendingCount = statistics.pending_count || 0;
  const errorRate = Math.round((metrics.error_rate || 0) * 100);
  const daysWithoutError = metrics.days_without_error || 0;

  return (
    <div className="space-y-4">
      {/* Top Row - Key Metrics */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Gesamte Vorschläge"
          value={totalDecisions.toLocaleString('de-DE')}
          subtitle="Letzte 30 Tage"
          icon={<Activity className="h-4 w-4 text-muted-foreground" />}
        />

        <StatCard
          title="Durchschn. Konfidenz"
          value={`${avgConfidence}%`}
          subtitle={
            avgConfidence >= 80
              ? 'Ausgezeichnet'
              : avgConfidence >= 60
              ? 'Gut'
              : 'Verbesserungsbedarf'
          }
          icon={<TrendingUp className="h-4 w-4 text-muted-foreground" />}
          progressValue={avgConfidence}
          progressLabel={`${avgConfidence}/100`}
          trend={avgConfidence >= 80 ? 'up' : avgConfidence >= 60 ? 'neutral' : 'down'}
        />

        <StatCard
          title="Ausstehend"
          value={pendingCount}
          subtitle="Warten auf Genehmigung"
          icon={<Clock className="h-4 w-4 text-muted-foreground" />}
        />

        <StatCard
          title="Fehlerrate"
          value={`${errorRate}%`}
          subtitle={
            daysWithoutError > 0
              ? `${daysWithoutError} Tage ohne Fehler`
              : 'Kürzlich Fehler aufgetreten'
          }
          icon={
            errorRate < 5 ? (
              <CheckCircle2 className="h-4 w-4 text-green-600" />
            ) : (
              <XCircle className="h-4 w-4 text-red-600" />
            )
          }
          progressValue={Math.max(0, 100 - errorRate)}
          progressLabel={`${100 - errorRate}% Genauigkeit`}
          trend={errorRate < 5 ? 'up' : errorRate < 10 ? 'neutral' : 'down'}
        />
      </div>

      {/* Bottom Row - Acceptance Metrics */}
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          title="Auto-Akzeptanz"
          value={`${autoAcceptanceRate}%`}
          subtitle={`${statistics.by_status.auto_accepted || 0} von ${totalDecisions} Vorschlägen`}
          icon={<CheckCircle2 className="h-4 w-4 text-green-600" />}
          progressValue={autoAcceptanceRate}
        />

        <StatCard
          title="Genehmigungs-Rate"
          value={`${approvalRate}%`}
          subtitle={`${statistics.by_status.approved || 0} manuell genehmigt`}
          icon={<CheckCircle2 className="h-4 w-4 text-blue-600" />}
          progressValue={approvalRate}
        />

        <StatCard
          title="Ablehnungs-Rate"
          value={`${rejectionRate}%`}
          subtitle={`${statistics.by_status.rejected || 0} abgelehnt`}
          icon={<XCircle className="h-4 w-4 text-red-600" />}
          progressValue={rejectionRate}
        />
      </div>

      {/* Additional Info */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Verteilung nach Vorschlagstyp</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {Object.entries(statistics.by_type).map(([type, count]) => {
              const percentage = totalDecisions > 0 ? (count / totalDecisions) * 100 : 0;
              return (
                <div key={type} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground capitalize">
                      {type.replace(/_/g, ' ')}
                    </span>
                    <span className="font-medium">
                      {count} ({Math.round(percentage)}%)
                    </span>
                  </div>
                  <Progress value={percentage} className="h-1" />
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
