/**
 * Risk Overview Widget
 *
 * Zeigt Risiko-Übersicht für Geschäftspartner an
 */

import { useQuery } from '@tanstack/react-query';
import { WidgetWrapper } from './WidgetWrapper';
import { AlertTriangle, Shield } from 'lucide-react';
import type { Widget } from '../../types';
import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface RiskOverviewWidgetProps {
  widget: Widget;
  onRemove?: () => void;
  onSettings?: () => void;
  isEditing?: boolean;
}

interface RiskStats {
  high_risk_count: number;
  medium_risk_count: number;
  low_risk_count: number;
  average_risk_score: number;
  top_risks: Array<{
    entity_id: string;
    entity_name: string;
    risk_score: number;
    primary_risk_factor: string;
  }>;
}

export function RiskOverviewWidget({
  widget,
  onRemove,
  onSettings,
  isEditing,
}: RiskOverviewWidgetProps) {
  const { data, isLoading } = useQuery<RiskStats>({
    queryKey: ['widget-data', 'risk-overview', widget.id],
    queryFn: async () => {
      const response = await fetch('/api/v1/risk/stats', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Fehler beim Laden der Risiko-Daten');
      return response.json();
    },
  });

  // Rueckgabetyp auf die echten Badge-Variants eingeengt; 'warning'/'success'
  // existieren als Variant nicht (rendert sonst unstyled) -> outline + Farbe
  const getRiskLevel = (
    score: number
  ): { label: string; variant: BadgeProps['variant']; className?: string } => {
    if (score >= 75) return { label: 'Hoch', variant: 'destructive' };
    if (score >= 50)
      return { label: 'Mittel', variant: 'outline', className: 'border-orange-500 text-orange-600' };
    return { label: 'Niedrig', variant: 'outline', className: 'border-green-500 text-green-600' };
  };

  const getRiskColor = (score: number) => {
    if (score >= 75) return 'text-red-500';
    if (score >= 50) return 'text-orange-500';
    return 'text-green-500';
  };

  return (
    <WidgetWrapper
      title={widget.title}
      onRemove={onRemove}
      onSettings={onSettings}
      isEditing={isEditing}
    >
      {isLoading ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-sm text-muted-foreground">Lädt...</div>
        </div>
      ) : data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="text-center p-3 rounded-lg border border-red-200 bg-red-50 dark:bg-red-950/20">
              <div className="text-2xl font-bold text-red-600">
                {data.high_risk_count}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Hohes Risiko
              </div>
            </div>
            <div className="text-center p-3 rounded-lg border border-orange-200 bg-orange-50 dark:bg-orange-950/20">
              <div className="text-2xl font-bold text-orange-600">
                {data.medium_risk_count}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Mittleres Risiko
              </div>
            </div>
            <div className="text-center p-3 rounded-lg border border-green-200 bg-green-50 dark:bg-green-950/20">
              <div className="text-2xl font-bold text-green-600">
                {data.low_risk_count}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Niedriges Risiko
              </div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-muted/50">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">
                Durchschnittliches Risiko
              </span>
              <span
                className={`font-bold ${getRiskColor(
                  data.average_risk_score
                )}`}
              >
                {data.average_risk_score.toFixed(1)}
              </span>
            </div>
            <Progress value={data.average_risk_score} className="h-2" />
          </div>

          {data.top_risks && data.top_risks.length > 0 && (
            <div>
              <div className="text-sm font-medium mb-2 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-orange-500" />
                Höchste Risiken
              </div>
              <div className="space-y-2">
                {data.top_risks.slice(0, 3).map((risk) => (
                  <div
                    key={risk.entity_id}
                    className="flex items-center justify-between p-2 rounded border text-sm"
                  >
                    <div className="flex-1 truncate">
                      <div className="font-medium truncate">
                        {risk.entity_name}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {risk.primary_risk_factor}
                      </div>
                    </div>
                    <Badge
                      variant={getRiskLevel(risk.risk_score).variant}
                      className={cn('ml-2', getRiskLevel(risk.risk_score).className)}
                    >
                      {risk.risk_score.toFixed(0)}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center h-full text-center p-4">
          <Shield className="h-8 w-8 text-muted-foreground mb-2" />
          <div className="text-sm text-muted-foreground">
            Keine Risiko-Daten verfügbar
          </div>
        </div>
      )}
    </WidgetWrapper>
  );
}
