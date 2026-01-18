/**
 * Supplier Score Card Component
 *
 * Zeigt den Score und Tier eines Lieferanten.
 */

import { TrendingUp, TrendingDown, Minus, Package, Calendar, DollarSign } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import type { SupplierRanking, SupplierTier, ScoreTrend } from '../types/supplier-ranking-types';
import { TIER_COLORS, TIER_LABELS } from '../types/supplier-ranking-types';

interface SupplierScoreCardProps {
  ranking: SupplierRanking;
  compact?: boolean;
  showDetails?: boolean;
  className?: string;
}

export function SupplierScoreCard({
  ranking,
  compact = false,
  showDetails = true,
  className,
}: SupplierScoreCardProps) {
  const tierColors = TIER_COLORS[ranking.tier];

  if (compact) {
    return (
      <div
        className={cn(
          'flex items-center justify-between p-3 rounded-lg border',
          tierColors.bg,
          className
        )}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-xl">{tierColors.icon}</span>
          <div className="min-w-0">
            <p className="font-medium truncate">{ranking.entityName}</p>
            <p className={cn('text-xs', tierColors.text)}>
              {TIER_LABELS[ranking.tier]}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ScoreBadge score={ranking.overallScore} tier={ranking.tier} />
          <TrendIcon trend={ranking.scoreTrend} />
        </div>
      </div>
    );
  }

  return (
    <Card className={cn(tierColors.bg, 'border-2', tierColors.border, className)}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <span className="text-3xl">{tierColors.icon}</span>
            <div>
              <CardTitle className="text-lg">{ranking.entityName}</CardTitle>
              <Badge className={cn('mt-1', tierColors.bg, tierColors.text, 'border-0')}>
                {TIER_LABELS[ranking.tier]}
              </Badge>
            </div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold">{Math.round(ranking.overallScore)}</div>
            <div className="text-sm text-muted-foreground">/ 100</div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Score Progress */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Gesamtscore</span>
            <div className="flex items-center gap-2">
              {ranking.previousScore !== null && (
                <span className="text-xs text-muted-foreground">
                  (vorher: {Math.round(ranking.previousScore)})
                </span>
              )}
              <TrendIcon trend={ranking.scoreTrend} showLabel />
            </div>
          </div>
          <Progress
            value={ranking.overallScore}
            className="h-2"
            indicatorClassName={getTierProgressColor(ranking.tier)}
          />
        </div>

        {showDetails && (
          <>
            {/* Key Metrics */}
            <div className="grid grid-cols-3 gap-4 pt-2">
              <MetricItem
                icon={Package}
                label="Bestellungen"
                value={ranking.totalOrders.toString()}
              />
              <MetricItem
                icon={DollarSign}
                label="Volumen"
                value={formatCurrency(ranking.totalVolume)}
              />
              <MetricItem
                icon={Calendar}
                label="Letzte Bestellung"
                value={
                  ranking.lastOrderDate
                    ? ranking.lastOrderDate.toLocaleDateString('de-DE')
                    : '-'
                }
              />
            </div>

            {/* Recommendations */}
            {ranking.recommendations.length > 0 && (
              <div className="pt-2 border-t border-border/50">
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Empfehlungen
                </p>
                <ul className="space-y-1">
                  {ranking.recommendations.slice(0, 2).map((rec, idx) => (
                    <li key={idx} className="text-sm">
                      • {rec}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Score Badge
 */
interface ScoreBadgeProps {
  score: number;
  tier: SupplierTier;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function ScoreBadge({ score, tier, size = 'md', className }: ScoreBadgeProps) {
  const tierColors = TIER_COLORS[tier];

  const sizeClasses = {
    sm: 'text-sm px-2 py-0.5 min-w-[40px]',
    md: 'text-base px-3 py-1 min-w-[50px]',
    lg: 'text-lg px-4 py-1.5 min-w-[60px]',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center font-bold rounded-full',
        tierColors.bg,
        tierColors.text,
        sizeClasses[size],
        className
      )}
    >
      {Math.round(score)}
    </span>
  );
}

/**
 * Tier Badge
 */
interface TierBadgeProps {
  tier: SupplierTier;
  showIcon?: boolean;
  className?: string;
}

export function TierBadge({ tier, showIcon = true, className }: TierBadgeProps) {
  const tierColors = TIER_COLORS[tier];

  return (
    <Badge className={cn(tierColors.bg, tierColors.text, 'border-0 gap-1', className)}>
      {showIcon && <span>{tierColors.icon}</span>}
      {TIER_LABELS[tier]}
    </Badge>
  );
}

/**
 * Trend Icon
 */
interface TrendIconProps {
  trend: ScoreTrend;
  showLabel?: boolean;
  className?: string;
}

function TrendIcon({ trend, showLabel = false, className }: TrendIconProps) {
  const config = {
    improving: {
      Icon: TrendingUp,
      color: 'text-green-600 dark:text-green-400',
      label: 'Verbessernd',
    },
    declining: {
      Icon: TrendingDown,
      color: 'text-red-600 dark:text-red-400',
      label: 'Verschlechternd',
    },
    stable: {
      Icon: Minus,
      color: 'text-gray-500 dark:text-gray-400',
      label: 'Stabil',
    },
  };

  const { Icon, color, label } = config[trend];

  return (
    <span className={cn('inline-flex items-center gap-1', color, className)}>
      <Icon className="h-4 w-4" />
      {showLabel && <span className="text-xs">{label}</span>}
    </span>
  );
}

/**
 * Metric Item
 */
interface MetricItemProps {
  icon: React.ElementType;
  label: string;
  value: string;
}

function MetricItem({ icon: Icon, label, value }: MetricItemProps) {
  return (
    <div className="text-center">
      <Icon className="h-4 w-4 mx-auto text-muted-foreground mb-1" />
      <p className="text-sm font-medium">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

// Helper Functions
function getTierProgressColor(tier: SupplierTier): string {
  switch (tier) {
    case 'platinum':
      return 'bg-violet-500';
    case 'gold':
      return 'bg-amber-500';
    case 'silver':
      return 'bg-slate-500';
    case 'bronze':
      return 'bg-orange-500';
    case 'critical':
      return 'bg-red-500';
    default:
      return 'bg-gray-500';
  }
}

function formatCurrency(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M €`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K €`;
  }
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value);
}
