/**
 * SLADashboard Component
 * Display SLA metrics and bottleneck analysis
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, CheckCircle2, Clock, TrendingUp } from 'lucide-react';
import { useSLAMetrics } from '../hooks/use-approval-enhanced-queries';
import { UI_LABELS } from '../types/approval-enhanced-types';
import { cn } from '@/lib/utils';

export function SLADashboard() {
  const { data: metrics, isLoading } = useSLAMetrics();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Card key={i}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-4" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-16 mb-2" />
                <Skeleton className="h-3 w-32" />
              </CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-48" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-48 w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!metrics) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        Keine SLA-Metriken verfügbar
      </div>
    );
  }

  const breachRate =
    metrics.totalApprovals > 0
      ? (metrics.slaBreachCount / metrics.totalApprovals) * 100
      : 0;

  return (
    <div className="space-y-6">
      {/* Metric Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {/* Avg Approval Time */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {UI_LABELS.sla.avgApprovalTime}
            </CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metrics.avgApprovalTimeHours.toFixed(1)}h
            </div>
            <p className="text-xs text-muted-foreground">
              Durchschnittliche Bearbeitungszeit
            </p>
          </CardContent>
        </Card>

        {/* SLA Breaches */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {UI_LABELS.sla.breachCount}
            </CardTitle>
            <AlertCircle
              className={cn(
                'h-4 w-4',
                metrics.slaBreachCount > 0 ? 'text-destructive' : 'text-muted-foreground'
              )}
            />
          </CardHeader>
          <CardContent>
            <div
              className={cn(
                'text-2xl font-bold',
                metrics.slaBreachCount > 0 && 'text-destructive'
              )}
            >
              {metrics.slaBreachCount}
            </div>
            <p className="text-xs text-muted-foreground">
              Verstöße ({breachRate.toFixed(1)}%)
            </p>
          </CardContent>
        </Card>

        {/* Total Approvals */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {UI_LABELS.sla.totalApprovals}
            </CardTitle>
            <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.totalApprovals}</div>
            <p className="text-xs text-muted-foreground">Genehmigungen insgesamt</p>
          </CardContent>
        </Card>

        {/* Pending Count */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {UI_LABELS.sla.pendingCount}
            </CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.pendingCount}</div>
            <p className="text-xs text-muted-foreground">Ausstehende Genehmigungen</p>
          </CardContent>
        </Card>
      </div>

      {/* Bottleneck Stages */}
      <Card>
        <CardHeader>
          <CardTitle>{UI_LABELS.sla.bottleneckStages}</CardTitle>
        </CardHeader>
        <CardContent>
          {metrics.bottleneckStages.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              Keine Engpässe erkannt
            </div>
          ) : (
            <div className="space-y-4">
              {metrics.bottleneckStages.map((stage) => {
                const avgHours = stage.avgDurationHours;
                const severity =
                  avgHours > 48 ? 'high' : avgHours > 24 ? 'medium' : 'low';

                return (
                  <div key={stage.stage} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{stage.stage}</span>
                        <Badge
                          variant={
                            severity === 'high'
                              ? 'destructive'
                              : severity === 'medium'
                                ? 'default'
                                : 'secondary'
                          }
                        >
                          {avgHours.toFixed(1)}h durchschnittlich
                        </Badge>
                      </div>
                      <span className="text-sm text-muted-foreground">
                        {stage.count} Vorgänge
                      </span>
                    </div>
                    <div className="relative h-2 bg-secondary rounded-full overflow-hidden">
                      <div
                        className={cn(
                          'absolute left-0 top-0 h-full rounded-full transition-all',
                          severity === 'high' && 'bg-destructive',
                          severity === 'medium' && 'bg-yellow-500',
                          severity === 'low' && 'bg-green-500'
                        )}
                        style={{
                          width: `${Math.min((avgHours / 72) * 100, 100)}%`,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
