/**
 * Drift Status Card - Drift Detection Anzeige
 *
 * Zeigt den aktuellen Drift-Status und ermoeglicht
 * manuelle Drift-Detection.
 */

import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  TrendingDown,
  BarChart2,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import {
  useRunDriftDetection,
  useResetDriftReference,
} from '../hooks/useAIDecisions';
import type { DriftStatus, DriftSeverity } from '../types/ai-types';

interface DriftStatusCardProps {
  driftStatus: DriftStatus | undefined;
}

export function DriftStatusCard({ driftStatus }: DriftStatusCardProps) {
  const runDriftMutation = useRunDriftDetection();
  const resetMutation = useResetDriftReference();

  if (!driftStatus) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="h-48 bg-muted animate-pulse rounded-lg" />
        </CardContent>
      </Card>
    );
  }

  const severityConfig: Record<DriftSeverity, { color: string; label: string; icon: React.ElementType }> = {
    none: { color: 'text-green-500', label: 'Kein Drift', icon: CheckCircle2 },
    low: { color: 'text-yellow-500', label: 'Geringer Drift', icon: TrendingDown },
    medium: { color: 'text-orange-500', label: 'Mittlerer Drift', icon: AlertTriangle },
    high: { color: 'text-red-500', label: 'Hoher Drift', icon: AlertTriangle },
    critical: { color: 'text-red-600', label: 'Kritischer Drift', icon: AlertTriangle },
  };

  const lastReport = driftStatus.last_report;
  const severity = lastReport?.severity ?? 'none';
  const config = severityConfig[severity];
  const SeverityIcon = config.icon;

  const samplesProgress =
    driftStatus.min_samples_required > 0
      ? (driftStatus.current_samples / driftStatus.min_samples_required) * 100
      : 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5" />
            <CardTitle className="text-lg">Drift Detection</CardTitle>
          </div>
          <Badge
            variant={driftStatus.ready_for_detection ? 'default' : 'secondary'}
          >
            {driftStatus.ready_for_detection ? 'Bereit' : 'Sammelt Daten'}
          </Badge>
        </div>
        <CardDescription>
          Erkennung von Veraenderungen in den Eingabedaten
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Current Status */}
        {lastReport ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <SeverityIcon className={cn('w-5 h-5', config.color)} />
                <span className={cn('font-medium', config.color)}>
                  {config.label}
                </span>
              </div>
              <span className="text-2xl font-bold">
                {(lastReport.overall_drift_score * 100).toFixed(1)}%
              </span>
            </div>

            <Progress
              value={lastReport.overall_drift_score * 100}
              className={cn(
                'h-2',
                lastReport.overall_drift_score > driftStatus.drift_threshold
                  ? '[&>div]:bg-red-500'
                  : '[&>div]:bg-green-500'
              )}
            />

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Referenz-Samples</span>
                <p className="font-medium">{lastReport.samples_reference}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Aktuelle Samples</span>
                <p className="font-medium">{lastReport.samples_current}</p>
              </div>
            </div>

            {/* Feature Drifts */}
            {lastReport.feature_drifts.length > 0 && (
              <div className="space-y-2 pt-3 border-t">
                <span className="text-sm text-muted-foreground">
                  Top Feature Drifts
                </span>
                <div className="space-y-1">
                  {lastReport.feature_drifts
                    .filter((fd) => fd.is_drifted)
                    .slice(0, 3)
                    .map((fd) => (
                      <div
                        key={fd.feature_name}
                        className="flex items-center justify-between text-sm"
                      >
                        <span className="font-mono text-xs">{fd.feature_name}</span>
                        <span className="text-red-500 font-medium">
                          {(fd.drift_score * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Recommendations */}
            {lastReport.recommendations.length > 0 && (
              <div className="space-y-2 pt-3 border-t">
                <span className="text-sm text-muted-foreground">Empfehlungen</span>
                <ul className="text-sm space-y-1">
                  {lastReport.recommendations.slice(0, 2).map((rec, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-primary">•</span>
                      {rec}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="text-xs text-muted-foreground">
              Letzter Check:{' '}
              {new Date(lastReport.timestamp).toLocaleString('de-DE')}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-muted-foreground">
              <BarChart2 className="w-5 h-5" />
              <span>Sammle Referenz-Daten...</span>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Samples gesammelt</span>
                <span>
                  {driftStatus.current_samples} / {driftStatus.min_samples_required}
                </span>
              </div>
              <Progress value={Math.min(samplesProgress, 100)} className="h-2" />
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-3 border-t">
          <Button
            variant="outline"
            size="sm"
            className="flex-1"
            onClick={() => runDriftMutation.mutate()}
            disabled={!driftStatus.ready_for_detection || runDriftMutation.isPending}
          >
            <RefreshCw
              className={cn(
                'w-4 h-4 mr-1',
                runDriftMutation.isPending && 'animate-spin'
              )}
            />
            {runDriftMutation.isPending ? 'Pruefe...' : 'Drift pruefen'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => resetMutation.mutate()}
            disabled={resetMutation.isPending}
          >
            Referenz zuruecksetzen
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
