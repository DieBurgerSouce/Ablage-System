/**
 * Risk Score Gauge Component
 *
 * Visualisiert den Risiko-Score als halbrunde Gauge.
 */

import { cn } from '@/lib/utils';

interface RiskScoreGaugeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

export function RiskScoreGauge({
  score,
  size = 'md',
  showLabel = true,
  className,
}: RiskScoreGaugeProps) {
  const normalizedScore = Math.max(0, Math.min(100, score));

  const getRiskLevel = (score: number) => {
    if (score < 25) return { level: 'Niedrig', color: 'text-green-600', bgColor: 'bg-green-500' };
    if (score < 50) return { level: 'Mittel', color: 'text-yellow-600', bgColor: 'bg-yellow-500' };
    if (score < 75) return { level: 'Hoch', color: 'text-orange-600', bgColor: 'bg-orange-500' };
    return { level: 'Kritisch', color: 'text-red-600', bgColor: 'bg-red-500' };
  };

  const { level, color, bgColor: _bgColor } = getRiskLevel(normalizedScore);

  const sizeClasses = {
    sm: { width: 'w-24', height: 'h-12', text: 'text-lg', label: 'text-xs' },
    md: { width: 'w-36', height: 'h-18', text: 'text-2xl', label: 'text-sm' },
    lg: { width: 'w-48', height: 'h-24', text: 'text-4xl', label: 'text-base' },
  };

  const { width, height, text, label } = sizeClasses[size];

  // Calculate rotation for the gauge needle (0 = left, 180 = right)
  const rotation = (normalizedScore / 100) * 180;

  return (
    <div className={cn('flex flex-col items-center', className)}>
      <div className={cn('relative', width, height)}>
        {/* Background arc */}
        <svg
          viewBox="0 0 100 50"
          className="w-full h-full"
          style={{ overflow: 'visible' }}
        >
          {/* Background track */}
          <path
            d="M 5 50 A 45 45 0 0 1 95 50"
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            className="text-muted"
          />
          {/* Colored segments */}
          <path
            d="M 5 50 A 45 45 0 0 1 27.5 14.5"
            fill="none"
            stroke="#22c55e"
            strokeWidth="8"
            strokeLinecap="round"
          />
          <path
            d="M 27.5 14.5 A 45 45 0 0 1 50 5"
            fill="none"
            stroke="#eab308"
            strokeWidth="8"
          />
          <path
            d="M 50 5 A 45 45 0 0 1 72.5 14.5"
            fill="none"
            stroke="#f97316"
            strokeWidth="8"
          />
          <path
            d="M 72.5 14.5 A 45 45 0 0 1 95 50"
            fill="none"
            stroke="#ef4444"
            strokeWidth="8"
            strokeLinecap="round"
          />
          {/* Needle */}
          <g transform={`rotate(${rotation - 90}, 50, 50)`}>
            <line
              x1="50"
              y1="50"
              x2="50"
              y2="12"
              stroke="currentColor"
              strokeWidth="2"
              className="text-foreground"
            />
            <circle cx="50" cy="50" r="4" fill="currentColor" className="text-foreground" />
          </g>
        </svg>
      </div>

      {/* Score display */}
      <div className="mt-2 text-center">
        <span className={cn('font-bold', text, color)}>{normalizedScore.toFixed(0)}</span>
        {showLabel && (
          <p className={cn('text-muted-foreground', label)}>{level}</p>
        )}
      </div>
    </div>
  );
}
