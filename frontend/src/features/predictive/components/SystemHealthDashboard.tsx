/**
 * SystemHealthDashboard - System-Gesundheits-Vorhersagen
 *
 * Zeigt prognostizierte Systemmetriken (VRAM, Queue, CPU etc.)
 * mit Schwellenwert-Balken und ETA-Badges.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, Activity, AlertTriangle, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useSystemHealth } from '../hooks/use-predictions';

const metricLabels: Record<string, string> = {
  vram: 'GPU VRAM',
  gpu_vram: 'GPU VRAM',
  queue: 'Warteschlange',
  queue_depth: 'Warteschlange',
  cpu: 'CPU-Auslastung',
  memory: 'Arbeitsspeicher',
  disk: 'Festplatte',
  disk_usage: 'Festplatte',
  ocr_quality: 'OCR-Qualitaet',
};

function getSeverityColor(severity: string) {
  switch (severity) {
    case 'critical':
      return 'text-red-500';
    case 'warning':
      return 'text-amber-500';
    default:
      return 'text-green-500';
  }
}

function getSeverityBarColor(severity: string) {
  switch (severity) {
    case 'critical':
      return 'bg-red-500';
    case 'warning':
      return 'bg-amber-500';
    default:
      return 'bg-green-500';
  }
}

export function SystemHealthDashboard() {
  const { data: metrics, isLoading, isError } = useSystemHealth();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Lade Systemvorhersagen...
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isError || !metrics) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          Systemdaten nicht verfuegbar
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-5 w-5" />
          Systemvorhersagen
        </CardTitle>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {metrics.map((metric) => {
            const label = metricLabels[metric.metric] || metric.metric;
            const percentage = Math.min(
              (metric.current_value / metric.threshold) * 100,
              100,
            );
            const severity =
              metric.severity ||
              (percentage > 85
                ? 'critical'
                : percentage > 65
                  ? 'warning'
                  : 'normal');

            return (
              <div
                key={metric.metric}
                className="p-3 rounded-lg border space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{label}</span>
                  {severity === 'critical' || severity === 'warning' ? (
                    <AlertTriangle
                      className={cn('h-4 w-4', getSeverityColor(severity))}
                    />
                  ) : (
                    <CheckCircle
                      className={cn('h-4 w-4', getSeverityColor(severity))}
                    />
                  )}
                </div>

                {/* Gauge-Balken */}
                <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-full transition-all',
                      getSeverityBarColor(severity),
                    )}
                    style={{ width: `${percentage}%` }}
                  />
                </div>

                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Aktuell: {metric.current_value.toFixed(1)}</span>
                  <span>Prognose: {metric.predicted_value.toFixed(1)}</span>
                </div>

                {metric.eta_minutes != null && metric.eta_minutes > 0 && (
                  <Badge variant="outline" className="text-[10px]">
                    Schwellenwert in{' '}
                    {metric.eta_minutes < 60
                      ? `${Math.round(metric.eta_minutes)} Min.`
                      : `${(metric.eta_minutes / 60).toFixed(1)} Std.`}
                  </Badge>
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
