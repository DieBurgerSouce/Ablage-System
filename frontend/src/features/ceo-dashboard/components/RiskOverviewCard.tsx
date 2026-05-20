/**
 * Risk Overview Card Component
 *
 * Displays risk summary and top risks.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { RiskOverview } from '../types/digital-twin-types';
import { getRiskColor } from '../types/digital-twin-types';
import { AlertTriangle } from 'lucide-react';

interface RiskOverviewCardProps {
  data: RiskOverview;
}

export function RiskOverviewCard({ data }: RiskOverviewCardProps) {
  const colors = getRiskColor(data.averageRiskScore);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5" />
          Risiko-Übersicht
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Average Risk Score */}
        <div className="text-center py-4">
          <div className="text-sm text-muted-foreground mb-2">
            Durchschnittlicher Risiko-Score
          </div>
          <div className={`text-4xl font-bold ${colors.text}`}>
            {Math.round(data.averageRiskScore)}
          </div>
        </div>

        {/* Risk Distribution */}
        <div className="grid grid-cols-3 gap-2">
          <div className="text-center p-3 rounded-lg bg-red-100 dark:bg-red-900/30">
            <div className="text-2xl font-bold text-red-700 dark:text-red-400">
              {data.highRiskCount}
            </div>
            <div className="text-xs text-muted-foreground mt-1">Hoch</div>
          </div>
          <div className="text-center p-3 rounded-lg bg-yellow-100 dark:bg-yellow-900/30">
            <div className="text-2xl font-bold text-yellow-700 dark:text-yellow-400">
              {data.mediumRiskCount}
            </div>
            <div className="text-xs text-muted-foreground mt-1">Mittel</div>
          </div>
          <div className="text-center p-3 rounded-lg bg-green-100 dark:bg-green-900/30">
            <div className="text-2xl font-bold text-green-700 dark:text-green-400">
              {data.lowRiskCount}
            </div>
            <div className="text-xs text-muted-foreground mt-1">Niedrig</div>
          </div>
        </div>

        {/* Top 5 Risks */}
        <div className="space-y-2">
          <div className="text-sm font-semibold text-muted-foreground">
            Top 5 Risiken
          </div>
          {data.topRisks.length > 0 ? (
            <div className="space-y-2">
              {data.topRisks.map((risk) => {
                const riskColors = getRiskColor(risk.riskScore);
                return (
                  <div
                    key={risk.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
                  >
                    <div className="flex-1">
                      <div className="font-medium text-sm">{risk.name}</div>
                      <div className="text-xs text-muted-foreground mt-1">
                        <Badge variant="outline" className="text-xs">
                          {risk.category}
                        </Badge>
                      </div>
                    </div>
                    <div className={`text-lg font-bold ${riskColors.text}`}>
                      {Math.round(risk.riskScore)}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-4 text-sm text-muted-foreground">
              Keine Hochrisiko-Entitäten gefunden
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
