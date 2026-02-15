// Hint Statistics - Overview of hint generation and action rates

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertCircle, TrendingUp, TrendingDown, Activity } from 'lucide-react';
import { useStatisticsQuery } from '../hooks/use-proactive-assistant-queries';
import { UI_LABELS, CATEGORY_CONFIG } from '../types/proactive-assistant-types';

export function HintStatistics() {
  const { data, isLoading, error } = useStatisticsQuery();

  if (error) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <p className="text-sm">
              {UI_LABELS.messages.errorLoadingDashboard}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <Skeleton className="h-24" />
            <Skeleton className="h-32" />
          </div>
        </CardContent>
      </Card>
    );
  }

  const actionRatePercent = Math.round(data.actionRate * 100);
  const dismissRatePercent = Math.round(data.dismissRate * 100);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" />
          <span>Statistiken</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Overall Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">
              {UI_LABELS.statistics.generated}
            </p>
            <p className="text-3xl font-bold">{data.totalGenerated}</p>
          </div>
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">
              {UI_LABELS.statistics.acted}
            </p>
            <p className="text-3xl font-bold text-green-600">
              {data.totalActed}
            </p>
            <div className="flex items-center gap-1 text-sm text-green-600">
              <TrendingUp className="h-3 w-3" />
              <span>{actionRatePercent}%</span>
            </div>
          </div>
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">
              {UI_LABELS.statistics.dismissed}
            </p>
            <p className="text-3xl font-bold text-gray-600">
              {data.totalDismissed}
            </p>
            <div className="flex items-center gap-1 text-sm text-gray-600">
              <TrendingDown className="h-3 w-3" />
              <span>{dismissRatePercent}%</span>
            </div>
          </div>
        </div>

        {/* Rate Bars */}
        <div className="space-y-3">
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium">
                {UI_LABELS.statistics.actionRate}
              </span>
              <span className="text-sm text-muted-foreground">
                {actionRatePercent}%
              </span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 transition-all"
                style={{ width: `${actionRatePercent}%` }}
              />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium">
                {UI_LABELS.statistics.dismissRate}
              </span>
              <span className="text-sm text-muted-foreground">
                {dismissRatePercent}%
              </span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-gray-500 transition-all"
                style={{ width: `${dismissRatePercent}%` }}
              />
            </div>
          </div>
        </div>

        {/* By Category */}
        <div className="space-y-4 pt-4 border-t">
          <h4 className="font-medium text-sm">Nach Kategorie</h4>
          {Object.entries(data.byCategory).map(([key, stats]) => {
            const config = CATEGORY_CONFIG[key as keyof typeof CATEGORY_CONFIG];
            const categoryActionRate = stats.generated > 0
              ? Math.round((stats.acted / stats.generated) * 100)
              : 0;

            return (
              <div
                key={key}
                className={`p-3 rounded-lg border ${config.borderColor} ${config.bgColor}`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{config.icon}</span>
                    <span className={`font-medium text-sm ${config.color}`}>
                      {config.label}
                    </span>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {categoryActionRate}% umgesetzt
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <span className="text-muted-foreground">Generiert: </span>
                    <span className="font-medium">{stats.generated}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Umgesetzt: </span>
                    <span className="font-medium text-green-600">
                      {stats.acted}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Abgelehnt: </span>
                    <span className="font-medium text-gray-600">
                      {stats.dismissed}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
