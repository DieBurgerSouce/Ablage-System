/**
 * Risk Factor Breakdown Component
 *
 * Zeigt die 5 Risikofaktoren mit Gewichtung und Beitrag.
 */

import { Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Progress } from '@/components/ui/progress';
import type { RiskFactor } from '../types/risk-types';
import {
  RISK_FACTOR_LABELS,
  RISK_FACTOR_DESCRIPTIONS,
  RISK_FACTOR_WEIGHTS,
} from '../types/risk-types';

interface RiskFactorBreakdownProps {
  factors: RiskFactor[];
  compact?: boolean;
  showWeights?: boolean;
  className?: string;
}

function getFactorColor(contribution: number): string {
  if (contribution >= 20) return 'bg-red-500';
  if (contribution >= 15) return 'bg-orange-500';
  if (contribution >= 10) return 'bg-yellow-500';
  if (contribution >= 5) return 'bg-green-500';
  return 'bg-green-300';
}

function formatRawValue(factor: RiskFactor): string {
  if (factor.rawValue === undefined || factor.rawValue === null) {
    return '-';
  }

  switch (factor.name) {
    case 'payment_delay':
      return `${factor.rawValue} Tage`;
    case 'default_rate':
      return `${(Number(factor.rawValue) * 100).toFixed(1)}%`;
    case 'invoice_volume':
      return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
        maximumFractionDigits: 0,
      }).format(Number(factor.rawValue));
    case 'document_frequency':
      return `${factor.rawValue}/Monat`;
    case 'relationship_age':
      return `${factor.rawValue} Monate`;
    default:
      return String(factor.rawValue);
  }
}

export function RiskFactorBreakdown({
  factors,
  compact = false,
  showWeights = true,
  className,
}: RiskFactorBreakdownProps) {
  // Sort by contribution (highest first)
  const sortedFactors = [...factors].sort(
    (a, b) => b.contribution - a.contribution
  );

  if (compact) {
    return (
      <div className={cn('space-y-2', className)}>
        {sortedFactors.map((factor) => (
          <div key={factor.name} className="flex items-center gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between text-xs">
                <span className="truncate text-muted-foreground">
                  {RISK_FACTOR_LABELS[factor.name]}
                </span>
                <span className="font-medium">
                  +{factor.contribution.toFixed(1)}
                </span>
              </div>
              <Progress
                value={factor.contribution * 4} // Scale to 0-100 (max contribution ~25)
                className="h-1.5 mt-1"
                indicatorClassName={getFactorColor(factor.contribution)}
              />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className={cn('space-y-4', className)}>
        {sortedFactors.map((factor) => (
          <div key={factor.name} className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-medium">
                  {RISK_FACTOR_LABELS[factor.name]}
                </span>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                  </TooltipTrigger>
                  <TooltipContent side="right" className="max-w-xs">
                    <p>{RISK_FACTOR_DESCRIPTIONS[factor.name]}</p>
                    {showWeights && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        Gewichtung: {(RISK_FACTOR_WEIGHTS[factor.name] * 100).toFixed(0)}%
                      </p>
                    )}
                  </TooltipContent>
                </Tooltip>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">
                  {formatRawValue(factor)}
                </span>
                <span
                  className={cn(
                    'text-sm font-bold min-w-[60px] text-right',
                    factor.contribution >= 15
                      ? 'text-red-600 dark:text-red-400'
                      : factor.contribution >= 10
                        ? 'text-orange-600 dark:text-orange-400'
                        : 'text-green-600 dark:text-green-400'
                  )}
                >
                  +{factor.contribution.toFixed(1)}
                </span>
              </div>
            </div>
            <Progress
              value={factor.contribution * 4}
              className="h-2"
              indicatorClassName={getFactorColor(factor.contribution)}
            />
          </div>
        ))}

        {/* Total */}
        <div className="pt-3 border-t border-border">
          <div className="flex items-center justify-between">
            <span className="font-semibold">Gesamt Risk-Score</span>
            <span className="text-lg font-bold">
              {factors.reduce((sum, f) => sum + f.contribution, 0).toFixed(1)}
            </span>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}

/**
 * Factor Contribution Bar Chart (horizontal)
 */
interface FactorContributionChartProps {
  factors: RiskFactor[];
  className?: string;
}

export function FactorContributionChart({
  factors,
  className,
}: FactorContributionChartProps) {
  const totalContribution = factors.reduce((sum, f) => sum + f.contribution, 0);

  // Sort by contribution
  const sortedFactors = [...factors].sort(
    (a, b) => b.contribution - a.contribution
  );

  const colors = [
    'bg-red-500',
    'bg-orange-500',
    'bg-yellow-500',
    'bg-green-500',
    'bg-blue-500',
  ];

  return (
    <div className={cn('space-y-3', className)}>
      {/* Stacked bar */}
      <div className="h-8 rounded-lg overflow-hidden flex">
        {sortedFactors.map((factor, index) => {
          const percentage = (factor.contribution / totalContribution) * 100;
          return (
            <TooltipProvider key={factor.name}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div
                    className={cn(
                      'h-full transition-all cursor-help',
                      colors[index % colors.length]
                    )}
                    style={{ width: `${percentage}%` }}
                  />
                </TooltipTrigger>
                <TooltipContent>
                  <p className="font-medium">{RISK_FACTOR_LABELS[factor.name]}</p>
                  <p className="text-xs text-muted-foreground">
                    Beitrag: {factor.contribution.toFixed(1)} ({percentage.toFixed(1)}%)
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {sortedFactors.map((factor, index) => (
          <div key={factor.name} className="flex items-center gap-1.5 text-xs">
            <div
              className={cn('w-3 h-3 rounded', colors[index % colors.length])}
            />
            <span className="text-muted-foreground">
              {RISK_FACTOR_LABELS[factor.name]}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
