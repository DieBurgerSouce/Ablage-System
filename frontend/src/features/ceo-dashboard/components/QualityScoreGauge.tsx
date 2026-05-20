/**
 * Quality Score Gauge Component
 *
 * Displays overall data quality score as a circular gauge.
 */

import { Card, CardContent } from '@/components/ui/card';
import {
  getQualityScoreColor,
  getQualityScoreLabel,
} from '../types/data-quality-types';

interface QualityScoreGaugeProps {
  score: number;
}

export function QualityScoreGauge({ score }: QualityScoreGaugeProps) {
  const colors = getQualityScoreColor(score);
  const label = getQualityScoreLabel(score);

  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex flex-col items-center">
          {/* Circular gauge visualization */}
          <div className="relative w-48 h-48 mb-4">
            <svg viewBox="0 0 200 200" className="w-full h-full transform -rotate-90">
              {/* Background circle */}
              <circle
                cx="100"
                cy="100"
                r="80"
                fill="none"
                stroke="currentColor"
                strokeWidth="20"
                className="text-muted/20"
              />
              {/* Score arc */}
              <circle
                cx="100"
                cy="100"
                r="80"
                fill="none"
                stroke="currentColor"
                strokeWidth="20"
                strokeDasharray={`${(score / 100) * 502.65} 502.65`}
                className={colors.text}
                strokeLinecap="round"
              />
            </svg>
            {/* Score label in center */}
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <div className={`text-5xl font-bold ${colors.text}`}>
                {Math.round(score)}
              </div>
              <div className="text-sm text-muted-foreground uppercase mt-2">
                {label}
              </div>
            </div>
          </div>

          <div className="text-center">
            <div className="text-lg font-semibold">Datenqualität</div>
            <div className="text-sm text-muted-foreground mt-1">
              Gesamtscore
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
