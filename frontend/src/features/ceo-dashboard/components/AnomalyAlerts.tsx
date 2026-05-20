/**
 * Anomaly Alerts Component
 *
 * Displays detected anomalies as collapsible alert cards.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { Anomaly } from '../types';
import { SEVERITY_COLORS, SEVERITY_LABELS } from '../types';
import { AlertTriangle, Info, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from 'date-fns';
import { de } from 'date-fns/locale';

interface AnomalyAlertsProps {
  anomalies: Anomaly[];
}

interface AnomalyCardProps {
  anomaly: Anomaly;
}

function AnomalyCard({ anomaly }: AnomalyCardProps) {
  const [expanded, setExpanded] = useState(false);
  const colors = SEVERITY_COLORS[anomaly.severity];

  const getIcon = () => {
    switch (anomaly.severity) {
      case 'critical':
        return <AlertTriangle className="w-5 h-5" />;
      case 'warning':
        return <AlertCircle className="w-5 h-5" />;
      case 'info':
      default:
        return <Info className="w-5 h-5" />;
    }
  };

  const formatRelativeTime = (date: Date) => {
    return formatDistanceToNow(date, { addSuffix: true, locale: de });
  };

  return (
    <div
      className={cn(
        'rounded-lg border-l-4 p-4',
        colors.bg,
        colors.border
      )}
    >
      <div className="flex items-start gap-3">
        <div className={colors.text}>{getIcon()}</div>
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <Badge
                  variant="outline"
                  className={cn('text-xs', colors.text, colors.border)}
                >
                  {SEVERITY_LABELS[anomaly.severity]}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {anomaly.metric}
                </span>
              </div>
              <div className="font-medium">{anomaly.message}</div>
              <div className="text-xs text-muted-foreground mt-1">
                {formatRelativeTime(anomaly.detectedAt)}
              </div>
            </div>
            {anomaly.details && Object.keys(anomaly.details).length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setExpanded(!expanded)}
                className="shrink-0"
              >
                {expanded ? (
                  <ChevronUp className="w-4 h-4" />
                ) : (
                  <ChevronDown className="w-4 h-4" />
                )}
              </Button>
            )}
          </div>

          {/* Expandable Details */}
          {expanded && anomaly.details && (
            <div className="mt-3 pt-3 border-t border-border">
              <div className="text-xs font-semibold text-muted-foreground mb-2">
                Details
              </div>
              <div className="space-y-1">
                {Object.entries(anomaly.details).map(([key, value]) => (
                  <div key={key} className="text-xs flex justify-between gap-2">
                    <span className="text-muted-foreground">{key}:</span>
                    <span className="font-mono">
                      {typeof value === 'object'
                        ? JSON.stringify(value)
                        : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function AnomalyAlerts({ anomalies }: AnomalyAlertsProps) {
  if (anomalies.length === 0) {
    return null;
  }

  // Sort by severity (critical > warning > info) and then by date
  const sortedAnomalies = [...anomalies].sort((a, b) => {
    const severityOrder = { critical: 0, warning: 1, info: 2 };
    const severityDiff = severityOrder[a.severity] - severityOrder[b.severity];
    if (severityDiff !== 0) return severityDiff;
    return b.detectedAt.getTime() - a.detectedAt.getTime();
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
          Erkannte Anomalien
          <Badge variant="secondary" className="ml-auto">
            {anomalies.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {sortedAnomalies.map((anomaly, index) => (
            <AnomalyCard key={`${anomaly.type}-${anomaly.detectedAt.getTime()}-${index}`} anomaly={anomaly} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
