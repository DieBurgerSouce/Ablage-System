// Reusable Stat Card Component
// Displays a single metric with optional trend badge

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { StatCardData } from '../types/analytics-types';
import { getTrendIcon, getTrendColor } from '../types/analytics-types';

interface StatCardProps {
  stat: StatCardData;
  className?: string;
}

export function StatCard({ stat, className }: StatCardProps) {
  const TrendIcon = getTrendIcon(stat.trend);
  const trendColor = getTrendColor(stat.trend);

  return (
    <Card className={cn('hover:shadow-md transition-shadow', className)}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {stat.label}
        </CardTitle>
        {TrendIcon && <TrendIcon className={cn('h-4 w-4', trendColor)} />}
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline justify-between">
          <div className="text-2xl font-bold">{stat.value}</div>
          {stat.trendValue && (
            <Badge
              variant={
                stat.trend === 'up'
                  ? 'default'
                  : stat.trend === 'down'
                    ? 'destructive'
                    : 'secondary'
              }
              className="ml-2"
            >
              {stat.trendValue}
            </Badge>
          )}
        </div>
        {stat.unit && (
          <p className="text-xs text-muted-foreground mt-1">{stat.unit}</p>
        )}
      </CardContent>
    </Card>
  );
}
