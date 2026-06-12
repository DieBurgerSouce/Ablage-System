/**
 * Ranking Factors Component
 *
 * Zeigt die 5 Bewertungskategorien eines Lieferanten.
 */

import {
  Clock,
  DollarSign,
  Shield,
  MessageCircle,
  CreditCard,
  TrendingUp,
  TrendingDown,
  Minus,
  Info,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Progress } from '@/components/ui/progress';
import type { CategoryScore, RankingCategory, CategoryTrend } from '../types/supplier-ranking-types';
import { CATEGORY_DESCRIPTIONS, CATEGORY_WEIGHTS } from '../types/supplier-ranking-types';

interface RankingFactorsProps {
  categoryScores: CategoryScore[];
  compact?: boolean;
  showWeights?: boolean;
  className?: string;
}

const CATEGORY_ICONS: Record<RankingCategory, React.ElementType> = {
  punctuality: Clock,
  price: DollarSign,
  reliability: Shield,
  communication: MessageCircle,
  payment_terms: CreditCard,
};

function getScoreColor(score: number): string {
  if (score >= 80) return 'bg-green-500';
  if (score >= 60) return 'bg-yellow-500';
  if (score >= 40) return 'bg-orange-500';
  return 'bg-red-500';
}

function getScoreTextColor(score: number): string {
  if (score >= 80) return 'text-green-600 dark:text-green-400';
  if (score >= 60) return 'text-yellow-600 dark:text-yellow-400';
  if (score >= 40) return 'text-orange-600 dark:text-orange-400';
  return 'text-red-600 dark:text-red-400';
}

export function RankingFactors({
  categoryScores,
  compact = false,
  showWeights = true,
  className,
}: RankingFactorsProps) {
  // Sort by weight (most important first)
  const sortedScores = [...categoryScores].sort((a, b) => b.weight - a.weight);

  if (compact) {
    return (
      <div className={cn('space-y-2', className)}>
        {sortedScores.map((cs) => {
          const Icon = CATEGORY_ICONS[cs.category];
          return (
            <div key={cs.category} className="flex items-center gap-2">
              <Icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between text-xs">
                  <span className="truncate text-muted-foreground">
                    {cs.categoryLabel}
                  </span>
                  <span className={cn('font-medium', getScoreTextColor(cs.score))}>
                    {Math.round(cs.score)}
                  </span>
                </div>
                <Progress
                  value={cs.score}
                  className="h-1.5 mt-1"
                  indicatorClassName={getScoreColor(cs.score)}
                />
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className={cn('space-y-4', className)}>
        {sortedScores.map((cs) => {
          const Icon = CATEGORY_ICONS[cs.category];
          return (
            <div key={cs.category} className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Icon className="h-5 w-5 text-muted-foreground" />
                  <span className="font-medium">{cs.categoryLabel}</span>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                    </TooltipTrigger>
                    <TooltipContent side="right" className="max-w-xs">
                      <p>{CATEGORY_DESCRIPTIONS[cs.category]}</p>
                      {showWeights && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Gewichtung: {(CATEGORY_WEIGHTS[cs.category] * 100).toFixed(0)}%
                        </p>
                      )}
                      {cs.dataPoints > 0 && (
                        <p className="text-xs text-muted-foreground">
                          Basiert auf {cs.dataPoints} Datenpunkten
                        </p>
                      )}
                    </TooltipContent>
                  </Tooltip>
                </div>
                <div className="flex items-center gap-3">
                  <TrendIndicator trend={cs.trend} />
                  <span className={cn('text-lg font-bold min-w-[40px] text-right', getScoreTextColor(cs.score))}>
                    {Math.round(cs.score)}
                  </span>
                </div>
              </div>
              <Progress
                value={cs.score}
                className="h-2"
                indicatorClassName={getScoreColor(cs.score)}
              />
              {showWeights && (
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Gewichtung: {(cs.weight * 100).toFixed(0)}%</span>
                  <span>Datenpunkte: {cs.dataPoints}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </TooltipProvider>
  );
}

/**
 * Trend Indicator
 */
interface TrendIndicatorProps {
  trend: CategoryTrend;
  className?: string;
}

function TrendIndicator({ trend, className }: TrendIndicatorProps) {
  const config = {
    up: {
      Icon: TrendingUp,
      color: 'text-green-600 dark:text-green-400',
    },
    down: {
      Icon: TrendingDown,
      color: 'text-red-600 dark:text-red-400',
    },
    stable: {
      Icon: Minus,
      color: 'text-gray-500 dark:text-gray-400',
    },
  };

  const { Icon, color } = config[trend];

  return <Icon className={cn('h-4 w-4', color, className)} />;
}

/**
 * Radar Chart for Category Scores (simplified bar version)
 */
interface CategoryRadarChartProps {
  categoryScores: CategoryScore[];
  className?: string;
}

export function CategoryComparisonChart({
  categoryScores,
  className,
}: CategoryRadarChartProps) {
  const sortedScores = [...categoryScores].sort((a, b) => b.weight - a.weight);

  return (
    <div className={cn('space-y-3', className)}>
      {sortedScores.map((cs) => {
        const Icon = CATEGORY_ICONS[cs.category];
        return (
          <div key={cs.category} className="flex items-center gap-3">
            <Icon className="h-5 w-5 text-muted-foreground flex-shrink-0" />
            <div className="flex-1">
              <div className="h-6 bg-muted rounded-full overflow-hidden relative">
                <div
                  className={cn('h-full rounded-full transition-all', getScoreColor(cs.score))}
                  style={{ width: `${cs.score}%` }}
                />
                <span className="absolute inset-0 flex items-center justify-center text-xs font-medium">
                  {cs.categoryLabel}: {Math.round(cs.score)}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Category Score Summary (for comparison)
 */
interface CategoryScoreSummaryProps {
  categoryScores: CategoryScore[];
  showLabels?: boolean;
  className?: string;
}

export function CategoryScoreSummary({
  categoryScores,
  showLabels = false,
  className,
}: CategoryScoreSummaryProps) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      {categoryScores.map((cs) => {
        const Icon = CATEGORY_ICONS[cs.category];
        return (
          <TooltipProvider key={cs.category}>
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  className={cn(
                    'flex items-center gap-1 px-2 py-1 rounded-full text-xs',
                    cs.score >= 80
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : cs.score >= 60
                        ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                        : cs.score >= 40
                          ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                          : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                  )}
                >
                  <Icon className="h-3 w-3" />
                  {showLabels && <span className="truncate max-w-[60px]">{cs.categoryLabel}</span>}
                  <span className="font-medium">{Math.round(cs.score)}</span>
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p className="font-medium">{cs.categoryLabel}</p>
                <p className="text-xs text-muted-foreground">
                  Score: {cs.score.toFixed(1)} / 100
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      })}
    </div>
  );
}
