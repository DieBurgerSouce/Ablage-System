/**
 * Risk Score Gauge Component
 *
 * Visuelle Anzeige des Risiko-Scores als Gauge/Tachometer.
 */

import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import {
  getRiskLevel,
  RISK_LEVEL_COLORS,
  RISK_LEVEL_LABELS,
  type RiskLevel,
} from '../types/risk-types';

interface RiskScoreGaugeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  showPercentage?: boolean;
  className?: string;
}

const SIZE_CONFIG = {
  sm: {
    diameter: 80,
    strokeWidth: 6,
    fontSize: 'text-lg',
    labelSize: 'text-xs',
  },
  md: {
    diameter: 120,
    strokeWidth: 8,
    fontSize: 'text-2xl',
    labelSize: 'text-sm',
  },
  lg: {
    diameter: 160,
    strokeWidth: 10,
    fontSize: 'text-3xl',
    labelSize: 'text-base',
  },
};

function getGaugeColor(level: RiskLevel): string {
  switch (level) {
    case 'low':
      return '#22c55e'; // green-500
    case 'medium':
      return '#eab308'; // yellow-500
    case 'high':
      return '#f97316'; // orange-500
    case 'critical':
      return '#ef4444'; // red-500
    default:
      return '#6b7280'; // gray-500
  }
}

export function RiskScoreGauge({
  score,
  size = 'md',
  showLabel = true,
  showPercentage = true,
  className,
}: RiskScoreGaugeProps) {
  const config = SIZE_CONFIG[size];
  const riskLevel = getRiskLevel(score);
  const colors = RISK_LEVEL_COLORS[riskLevel];

  // SVG calculations
  const radius = (config.diameter - config.strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const halfCircumference = circumference / 2;

  // Score as percentage of the half-circle (180 degrees)
  const normalizedScore = Math.min(100, Math.max(0, score));
  const offset = halfCircumference - (normalizedScore / 100) * halfCircumference;

  const gaugeColor = useMemo(() => getGaugeColor(riskLevel), [riskLevel]);

  return (
    <div className={cn('flex flex-col items-center', className)}>
      <div className="relative" style={{ width: config.diameter, height: config.diameter / 2 + 20 }}>
        <svg
          width={config.diameter}
          height={config.diameter / 2 + config.strokeWidth}
          viewBox={`0 0 ${config.diameter} ${config.diameter / 2 + config.strokeWidth}`}
          className="overflow-visible"
        >
          {/* Background arc */}
          <path
            d={`M ${config.strokeWidth / 2} ${config.diameter / 2}
                A ${radius} ${radius} 0 0 1 ${config.diameter - config.strokeWidth / 2} ${config.diameter / 2}`}
            fill="none"
            stroke="currentColor"
            strokeWidth={config.strokeWidth}
            strokeLinecap="round"
            className="text-muted/20"
          />

          {/* Score arc */}
          <path
            d={`M ${config.strokeWidth / 2} ${config.diameter / 2}
                A ${radius} ${radius} 0 0 1 ${config.diameter - config.strokeWidth / 2} ${config.diameter / 2}`}
            fill="none"
            stroke={gaugeColor}
            strokeWidth={config.strokeWidth}
            strokeLinecap="round"
            strokeDasharray={halfCircumference}
            strokeDashoffset={offset}
            className="transition-all duration-500 ease-out"
          />

          {/* Tick marks */}
          {[0, 25, 50, 75, 100].map((tick) => {
            const angle = (tick / 100) * 180;
            const radian = (angle * Math.PI) / 180;
            const x1 = config.diameter / 2 - (radius - 4) * Math.cos(radian);
            const y1 = config.diameter / 2 - (radius - 4) * Math.sin(radian);
            const x2 = config.diameter / 2 - (radius + 4) * Math.cos(radian);
            const y2 = config.diameter / 2 - (radius + 4) * Math.sin(radian);

            return (
              <line
                key={tick}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke="currentColor"
                strokeWidth={tick === 50 ? 2 : 1}
                className="text-muted-foreground/40"
              />
            );
          })}
        </svg>

        {/* Score display */}
        <div
          className="absolute bottom-0 left-1/2 -translate-x-1/2 flex flex-col items-center"
        >
          <span className={cn('font-bold', config.fontSize, colors.text)}>
            {Math.round(score)}
          </span>
          {showPercentage && (
            <span className={cn('text-muted-foreground', config.labelSize)}>
              / 100
            </span>
          )}
        </div>
      </div>

      {showLabel && (
        <div
          className={cn(
            'mt-2 px-3 py-1 rounded-full text-sm font-medium',
            colors.bg,
            colors.text
          )}
        >
          {RISK_LEVEL_LABELS[riskLevel]}
        </div>
      )}
    </div>
  );
}

/**
 * Simple Risk Score Badge
 */
interface RiskScoreBadgeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
  showLevel?: boolean;
  className?: string;
}

export function RiskScoreBadge({
  score,
  size = 'md',
  showLevel = true,
  className,
}: RiskScoreBadgeProps) {
  const riskLevel = getRiskLevel(score);
  const colors = RISK_LEVEL_COLORS[riskLevel];

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
    lg: 'text-base px-3 py-1.5',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 font-medium rounded-full',
        colors.bg,
        colors.text,
        sizeClasses[size],
        className
      )}
    >
      <span className="font-bold">{Math.round(score)}</span>
      {showLevel && (
        <span className="text-current/70">
          {RISK_LEVEL_LABELS[riskLevel]}
        </span>
      )}
    </span>
  );
}

/**
 * Mini Risk Indicator (just colored dot + score)
 */
interface RiskIndicatorProps {
  score: number;
  className?: string;
}

export function RiskIndicator({ score, className }: RiskIndicatorProps) {
  const riskLevel = getRiskLevel(score);
  const gaugeColor = getGaugeColor(riskLevel);

  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span
        className="w-2 h-2 rounded-full"
        style={{ backgroundColor: gaugeColor }}
      />
      <span className="text-sm font-medium">{Math.round(score)}</span>
    </span>
  );
}
