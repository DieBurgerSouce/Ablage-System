// KPI Card Component
// Single KPI with value, trend arrow, and optional sparkline

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  KPIData,
  formatKPIValue,
  getTrendIcon,
  getTrendColor,
  UI_LABELS,
} from '../types/smart-dashboard-types';

interface KPICardProps {
  kpi: KPIData;
  className?: string;
}

export function KPICard({ kpi, className }: KPICardProps) {
  const TrendIcon = getTrendIcon(kpi.trend);
  const trendColor = getTrendColor(kpi.trend, kpi.color);
  const formattedValue = formatKPIValue(kpi.value, kpi.unit);

  return (
    <Card className={cn('hover:shadow-md transition-shadow', className)}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{kpi.label}</CardTitle>
        {TrendIcon && (
          <TrendIcon className={cn('h-4 w-4', trendColor)} />
        )}
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline justify-between">
          <div className="text-2xl font-bold">{formattedValue}</div>
          {kpi.trendPercentage !== undefined && (
            <Badge
              variant={kpi.trend === 'up' ? 'default' : kpi.trend === 'down' ? 'destructive' : 'secondary'}
              className="ml-2"
            >
              {kpi.trendPercentage > 0 ? '+' : ''}
              {kpi.trendPercentage.toFixed(1)}%
            </Badge>
          )}
        </div>

        {/* Sparkline Area (placeholder for now - would use a charting library) */}
        {kpi.sparklineData && kpi.sparklineData.length > 0 && (
          <div className="mt-3 h-12 flex items-end justify-between gap-0.5">
            {kpi.sparklineData.map((value, index) => {
              const max = Math.max(...kpi.sparklineData!);
              const min = Math.min(...kpi.sparklineData!);
              const range = max - min || 1;
              const heightPercent = ((value - min) / range) * 100;

              return (
                <div
                  key={index}
                  className={cn('flex-1 rounded-sm', trendColor.replace('text-', 'bg-'))}
                  style={{ height: `${heightPercent}%`, opacity: 0.6 }}
                />
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
