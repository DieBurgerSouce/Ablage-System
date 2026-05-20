/**
 * Health Score Gauge Component
 *
 * Displays the overall health score as a semi-circular gauge with dimension breakdowns.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import type { HealthScore } from '../types';
import { getHealthScoreColor } from '../types';
import { Activity } from 'lucide-react';

interface HealthScoreGaugeProps {
  healthScore: HealthScore;
}

export function HealthScoreGauge({ healthScore }: HealthScoreGaugeProps) {
  const { overallScore, label, dimensions } = healthScore;
  const colors = getHealthScoreColor(overallScore);

  // Ordered dimensions for display
  const orderedDimensions = [
    { key: 'financial', data: dimensions.financial },
    { key: 'operations', data: dimensions.operations },
    { key: 'risk', data: dimensions.risk },
    { key: 'compliance', data: dimensions.compliance },
  ] as const;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="w-5 h-5" />
          Unternehmensgesundheit
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Main Gauge */}
        <div className="flex flex-col items-center mb-6">
          {/* Semi-circular gauge visualization */}
          <div className="relative w-48 h-24 mb-4">
            <svg viewBox="0 0 200 100" className="w-full h-full">
              {/* Background arc */}
              <path
                d="M 10 90 A 90 90 0 0 1 190 90"
                fill="none"
                stroke="currentColor"
                strokeWidth="20"
                className="text-muted/20"
              />
              {/* Score arc */}
              <path
                d="M 10 90 A 90 90 0 0 1 190 90"
                fill="none"
                stroke="currentColor"
                strokeWidth="20"
                strokeDasharray={`${(overallScore / 100) * 283} 283`}
                className={colors.text}
                strokeLinecap="round"
              />
            </svg>
            {/* Score label in center */}
            <div className="absolute inset-0 flex flex-col items-center justify-end pb-2">
              <div className={`text-4xl font-bold ${colors.text}`}>
                {Math.round(overallScore)}
              </div>
              <div className="text-xs text-muted-foreground uppercase">
                {label}
              </div>
            </div>
          </div>
        </div>

        {/* Dimension Breakdown */}
        <div className="space-y-4">
          <div className="text-sm font-semibold text-muted-foreground">
            Dimensionen
          </div>
          {orderedDimensions.map(({ key, data }) => {
            const dimColors = getHealthScoreColor(data.score);
            return (
              <div key={key} className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{data.label}</span>
                  <div className="flex items-center gap-2">
                    <span className={`font-bold ${dimColors.text}`}>
                      {Math.round(data.score)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      ({Math.round(data.weight * 100)}%)
                    </span>
                  </div>
                </div>
                <Progress
                  value={data.score}
                  className="h-2"
                  indicatorClassName={dimColors.text}
                />
              </div>
            );
          })}
        </div>

        {/* Last Updated */}
        <div className="mt-6 pt-4 border-t border-border">
          <div className="text-xs text-muted-foreground">
            Aktualisiert:{' '}
            {healthScore.calculatedAt.toLocaleString('de-DE', {
              day: '2-digit',
              month: '2-digit',
              year: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
