/**
 * Risk Trend Chart Component
 *
 * Zeigt den Risiko-Trend über Zeit.
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
  Legend,
} from 'recharts';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import type { RiskStatistics } from '../types/risk-types';
import { UI_LABELS, getRiskLevel, RISK_LEVEL_COLORS } from '../types/risk-types';

interface RiskTrendChartProps {
  data: RiskStatistics['trend'];
  isLoading?: boolean;
  height?: number;
  showHighRiskCount?: boolean;
  className?: string;
}

export function RiskTrendChart({
  data,
  isLoading = false,
  height = 300,
  showHighRiskCount = true,
  className,
}: RiskTrendChartProps) {
  if (isLoading) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>{UI_LABELS.trendTitle}</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="w-full" style={{ height }} />
        </CardContent>
      </Card>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle>{UI_LABELS.trendTitle}</CardTitle>
        </CardHeader>
        <CardContent>
          <div
            className="flex items-center justify-center text-muted-foreground"
            style={{ height }}
          >
            Keine Trend-Daten verfügbar
          </div>
        </CardContent>
      </Card>
    );
  }

  // Format data for Recharts
  const chartData = data.map((item) => ({
    date: item.date.toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
    }),
    averageScore: Math.round(item.averageScore * 10) / 10,
    highRiskCount: item.highRiskCount,
  }));

  // Calculate trend
  const firstScore = data[0]?.averageScore ?? 0;
  const lastScore = data[data.length - 1]?.averageScore ?? 0;
  const scoreDiff = lastScore - firstScore;
  const trendPercentage =
    firstScore > 0 ? ((scoreDiff / firstScore) * 100).toFixed(1) : '0.0';

  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle>{UI_LABELS.trendTitle}</CardTitle>
        <TrendIndicator value={scoreDiff} percentage={trendPercentage} />
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
              </linearGradient>
              {showHighRiskCount && (
                <linearGradient id="countGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              )}
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              className="stroke-muted/30"
            />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              className="text-muted-foreground"
            />
            <YAxis
              yAxisId="left"
              domain={[0, 100]}
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              className="text-muted-foreground"
            />
            {showHighRiskCount && (
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                className="text-muted-foreground"
              />
            )}
            <Tooltip
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              labelStyle={{ fontWeight: 'bold', marginBottom: '4px' }}
              formatter={(value: number, name: string) => [
                name === 'averageScore' ? `${value} Punkte` : value,
                name === 'averageScore' ? 'Durchschn. Score' : 'Hoch-Risiko',
              ]}
            />
            {showHighRiskCount && (
              <Legend
                verticalAlign="top"
                height={36}
                formatter={(value) =>
                  value === 'averageScore' ? 'Durchschn. Score' : 'Hoch-Risiko Entities'
                }
              />
            )}
            <Area
              yAxisId="left"
              type="monotone"
              dataKey="averageScore"
              stroke="#f97316"
              strokeWidth={2}
              fill="url(#scoreGradient)"
            />
            {showHighRiskCount && (
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="highRiskCount"
                stroke="#ef4444"
                strokeWidth={2}
                dot={false}
              />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

/**
 * Trend Indicator Badge
 */
interface TrendIndicatorProps {
  value: number;
  percentage: string;
  className?: string;
}

function TrendIndicator({ value, percentage, className }: TrendIndicatorProps) {
  const isPositive = value > 0;
  const isNegative = value < 0;
  const isNeutral = value === 0;

  // For risk, lower is better, so negative change is good
  return (
    <div
      className={cn(
        'flex items-center gap-1 text-sm font-medium px-2 py-1 rounded-full',
        isNegative && 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
        isPositive && 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
        isNeutral && 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400',
        className
      )}
    >
      {isNegative && <TrendingDown className="h-3.5 w-3.5" />}
      {isPositive && <TrendingUp className="h-3.5 w-3.5" />}
      {isNeutral && <Minus className="h-3.5 w-3.5" />}
      <span>{isNegative ? '' : '+'}{percentage}%</span>
    </div>
  );
}

/**
 * Risk Distribution Chart (Pie/Donut alternative as bar)
 */
interface RiskDistributionChartProps {
  distribution: RiskStatistics['riskDistribution'];
  totalEntities: number;
  isLoading?: boolean;
  className?: string;
}

export function RiskDistributionChart({
  distribution,
  totalEntities,
  isLoading = false,
  className,
}: RiskDistributionChartProps) {
  if (isLoading) {
    return <Skeleton className={cn('h-[200px] w-full', className)} />;
  }

  const levels = [
    { key: 'low', label: 'Niedrig', count: distribution.low, color: 'bg-green-500' },
    { key: 'medium', label: 'Mittel', count: distribution.medium, color: 'bg-yellow-500' },
    { key: 'high', label: 'Hoch', count: distribution.high, color: 'bg-orange-500' },
    { key: 'critical', label: 'Kritisch', count: distribution.critical, color: 'bg-red-500' },
  ];

  return (
    <div className={cn('space-y-4', className)}>
      {/* Stacked bar */}
      <div className="h-6 rounded-full overflow-hidden flex bg-muted">
        {levels.map((level) => {
          const percentage = totalEntities > 0 ? (level.count / totalEntities) * 100 : 0;
          if (percentage === 0) return null;
          return (
            <div
              key={level.key}
              className={cn('h-full transition-all', level.color)}
              style={{ width: `${percentage}%` }}
              title={`${level.label}: ${level.count} (${percentage.toFixed(1)}%)`}
            />
          );
        })}
      </div>

      {/* Legend with counts */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {levels.map((level) => {
          const percentage =
            totalEntities > 0 ? ((level.count / totalEntities) * 100).toFixed(1) : '0.0';
          return (
            <div
              key={level.key}
              className="flex items-center gap-2 p-2 rounded-lg bg-muted/50"
            >
              <div className={cn('w-3 h-3 rounded-full', level.color)} />
              <div className="min-w-0">
                <p className="text-sm font-medium">{level.label}</p>
                <p className="text-xs text-muted-foreground">
                  {level.count} ({percentage}%)
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Entity Risk Mini Chart (for entity detail pages)
 */
interface EntityRiskMiniChartProps {
  data: Array<{ date: Date; score: number }>;
  height?: number;
  className?: string;
}

export function EntityRiskMiniChart({
  data,
  height = 100,
  className,
}: EntityRiskMiniChartProps) {
  if (!data || data.length === 0) {
    return (
      <div
        className={cn(
          'flex items-center justify-center text-sm text-muted-foreground',
          className
        )}
        style={{ height }}
      >
        Keine Verlaufsdaten
      </div>
    );
  }

  const chartData = data.map((item) => ({
    date: item.date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }),
    score: item.score,
  }));

  return (
    <div className={className}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData}>
          <Line
            type="monotone"
            dataKey="score"
            stroke="#f97316"
            strokeWidth={2}
            dot={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: '6px',
              fontSize: '11px',
              padding: '6px 10px',
            }}
            formatter={(value: number) => [`${value} Punkte`, 'Score']}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
