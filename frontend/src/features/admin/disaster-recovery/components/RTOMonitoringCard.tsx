/**
 * RTO Monitoring Card
 *
 * Zeigt RTO/RPO Metriken und Compliance.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Clock,
  Target,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  Activity,
} from 'lucide-react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import type { RTOMetrics } from '../api';

interface RTOMonitoringCardProps {
  metrics?: RTOMetrics;
  isLoading: boolean;
}

const formatDuration = (seconds: number) => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
};

const formatDate = (dateStr?: string) => {
  if (!dateStr) return '-';
  try {
    return format(new Date(dateStr), 'dd.MM.yyyy HH:mm', { locale: de });
  } catch {
    return dateStr;
  }
};

export function RTOMonitoringCard({ metrics, isLoading }: RTOMonitoringCardProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48 mb-2" />
          <Skeleton className="h-4 w-72" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Array.from({ length: 2 }).map((_, i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!metrics) {
    return null;
  }

  const rtoCompliant = metrics.rto_compliance_rate >= 0.9;
  const rpoCompliant = metrics.rpo_compliance_rate >= 0.9;
  const isHealthy = rtoCompliant && rpoCompliant && metrics.tests_in_last_90_days > 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            RTO/RPO Monitoring
          </CardTitle>
          <Badge variant={isHealthy ? 'default' : 'destructive'} className="gap-1">
            {isHealthy ? (
              <>
                <CheckCircle2 className="h-3 w-3" />
                Compliant
              </>
            ) : (
              <>
                <AlertTriangle className="h-3 w-3" />
                Warnung
              </>
            )}
          </Badge>
        </div>
        <CardDescription>Recovery Time & Recovery Point Objectives</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* RTO Section */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">Recovery Time Objective (RTO)</h4>
            <Badge variant={rtoCompliant ? 'default' : 'destructive'}>
              {(metrics.rto_compliance_rate * 100).toFixed(0)}% Compliance
            </Badge>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="p-3 rounded-lg bg-muted">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <Target className="h-3 w-3" />
                Ziel
              </div>
              <div className="text-lg font-bold">
                {formatDuration(metrics.target_rto_seconds)}
              </div>
            </div>

            <div className="p-3 rounded-lg bg-muted">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <Clock className="h-3 w-3" />
                Letzter Test
              </div>
              <div className="text-lg font-bold">
                {metrics.last_test_rto_seconds
                  ? formatDuration(metrics.last_test_rto_seconds)
                  : '-'}
              </div>
            </div>

            <div className="p-3 rounded-lg bg-muted">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                {metrics.average_rto_seconds &&
                metrics.average_rto_seconds <= metrics.target_rto_seconds ? (
                  <TrendingUp className="h-3 w-3 text-green-600" />
                ) : (
                  <TrendingDown className="h-3 w-3 text-red-600" />
                )}
                Durchschnitt
              </div>
              <div className="text-lg font-bold">
                {metrics.average_rto_seconds
                  ? formatDuration(metrics.average_rto_seconds)
                  : '-'}
              </div>
            </div>
          </div>

          {metrics.last_test_rto_seconds &&
            metrics.last_test_rto_seconds > metrics.target_rto_seconds && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>RTO-Ziel verfehlt</AlertTitle>
                <AlertDescription>
                  Letzter Test benötigte{' '}
                  {formatDuration(
                    metrics.last_test_rto_seconds - metrics.target_rto_seconds
                  )}{' '}
                  mehr als geplant. Bitte Prozesse überprüfen.
                </AlertDescription>
              </Alert>
            )}
        </div>

        {/* RPO Section */}
        <div className="space-y-3 pt-4 border-t">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">Recovery Point Objective (RPO)</h4>
            <Badge variant={rpoCompliant ? 'default' : 'destructive'}>
              {(metrics.rpo_compliance_rate * 100).toFixed(0)}% Compliance
            </Badge>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="p-3 rounded-lg bg-muted">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <Target className="h-3 w-3" />
                Ziel
              </div>
              <div className="text-lg font-bold">
                {formatDuration(metrics.target_rpo_seconds)}
              </div>
            </div>

            <div className="p-3 rounded-lg bg-muted">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <Clock className="h-3 w-3" />
                Letzter Test
              </div>
              <div className="text-lg font-bold">
                {metrics.last_test_rpo_seconds
                  ? formatDuration(metrics.last_test_rpo_seconds)
                  : '-'}
              </div>
            </div>

            <div className="p-3 rounded-lg bg-muted">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                {metrics.average_rpo_seconds &&
                metrics.average_rpo_seconds <= metrics.target_rpo_seconds ? (
                  <TrendingUp className="h-3 w-3 text-green-600" />
                ) : (
                  <TrendingDown className="h-3 w-3 text-red-600" />
                )}
                Durchschnitt
              </div>
              <div className="text-lg font-bold">
                {metrics.average_rpo_seconds
                  ? formatDuration(metrics.average_rpo_seconds)
                  : '-'}
              </div>
            </div>
          </div>

          {metrics.last_test_rpo_seconds &&
            metrics.last_test_rpo_seconds > metrics.target_rpo_seconds && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>RPO-Ziel verfehlt</AlertTitle>
                <AlertDescription>
                  Potentieller Datenverlust von{' '}
                  {formatDuration(
                    metrics.last_test_rpo_seconds - metrics.target_rpo_seconds
                  )}{' '}
                  über Ziel. Backup-Frequenz erhöhen.
                </AlertDescription>
              </Alert>
            )}
        </div>

        {/* Test Summary */}
        <div className="pt-4 border-t space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Tests (90 Tage)</span>
            <span className="font-mono font-medium">{metrics.tests_in_last_90_days}</span>
          </div>
          {metrics.last_test_date && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Letzter Test</span>
              <span className="font-mono">{formatDate(metrics.last_test_date)}</span>
            </div>
          )}
        </div>

        {metrics.tests_in_last_90_days === 0 && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Keine aktuellen Tests</AlertTitle>
            <AlertDescription>
              In den letzten 90 Tagen wurden keine Restore-Tests durchgeführt.
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
