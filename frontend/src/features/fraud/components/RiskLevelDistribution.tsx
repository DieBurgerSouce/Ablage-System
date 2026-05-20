/**
 * Risk Level Distribution
 *
 * Zeigt Verteilung der Alerts nach Risikostufe.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertTriangle } from 'lucide-react';
import type { FraudSummary } from '../api/fraud-api';

interface RiskLevelDistributionProps {
  summary: FraudSummary;
}

export function RiskLevelDistribution({ summary }: RiskLevelDistributionProps) {
  const total = summary.total_alerts || 1; // Prevent division by zero

  const levels = [
    {
      level: 'Kritisch',
      count: summary.critical,
      percentage: (summary.critical / total) * 100,
      color: 'bg-red-600',
      textColor: 'text-red-600',
    },
    {
      level: 'Hoch',
      count: summary.high,
      percentage: (summary.high / total) * 100,
      color: 'bg-orange-500',
      textColor: 'text-orange-500',
    },
    {
      level: 'Mittel',
      count: summary.medium,
      percentage: (summary.medium / total) * 100,
      color: 'bg-amber-500',
      textColor: 'text-amber-500',
    },
    {
      level: 'Niedrig',
      count: summary.low,
      percentage: (summary.low / total) * 100,
      color: 'bg-green-500',
      textColor: 'text-green-500',
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5" />
          Risikostufen
        </CardTitle>
        <CardDescription>
          Verteilung nach Schweregrad
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stacked Bar */}
        <div className="h-4 w-full flex rounded-full overflow-hidden">
          {levels.map((level) => (
            level.percentage > 0 && (
              <div
                key={level.level}
                className={`${level.color} transition-all`}
                style={{ width: `${level.percentage}%` }}
                title={`${level.level}: ${level.count}`}
              />
            )
          ))}
        </div>

        {/* Legend */}
        <div className="grid grid-cols-2 gap-4">
          {levels.map((level) => (
            <div key={level.level} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${level.color}`} />
                <span className="text-sm">{level.level}</span>
              </div>
              <span className={`font-bold ${level.textColor}`}>
                {level.count}
              </span>
            </div>
          ))}
        </div>

        {/* Total */}
        <div className="pt-4 border-t">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Gesamt</span>
            <span className="text-xl font-bold">{summary.total_alerts}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
