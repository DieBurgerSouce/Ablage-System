// Hint Dashboard Widget - Summary of hints by category

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { AlertCircle } from 'lucide-react';
import { useDashboardQuery } from '../hooks/use-proactive-assistant-queries';
import { CATEGORY_CONFIG, UI_LABELS } from '../types/proactive-assistant-types';

export function HintDashboardWidget() {
  const { data, isLoading, error } = useDashboardQuery();

  if (error) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <p className="text-sm">{UI_LABELS.messages.errorLoadingDashboard}</p>
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
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const categories = [
    {
      key: 'fristen' as const,
      count: data.byCategory.fristen,
    },
    {
      key: 'anomalien' as const,
      count: data.byCategory.anomalien,
    },
    {
      key: 'optimierung' as const,
      count: data.byCategory.optimierung,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Übersicht</span>
          <Badge variant="outline">{data.totalHints} Hinweise</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {categories.map(({ key, count }) => {
            const config = CATEGORY_CONFIG[key];
            return (
              <div
                key={key}
                className={`rounded-lg border ${config.borderColor} ${config.bgColor} p-4 transition-all hover:shadow-md`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-2xl">{config.icon}</span>
                  <span className={`text-3xl font-bold ${config.color}`}>
                    {count}
                  </span>
                </div>
                <p className={`text-sm font-medium ${config.color}`}>
                  {config.label}
                </p>
              </div>
            );
          })}
        </div>

        {/* Priority Summary */}
        <div className="mt-6 pt-4 border-t">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Nach Priorität:</span>
            <div className="flex gap-3">
              <span className="text-gray-600">
                Niedrig: {data.byPriority.low}
              </span>
              <span className="text-blue-600">
                Mittel: {data.byPriority.medium}
              </span>
              <span className="text-orange-600">
                Hoch: {data.byPriority.high}
              </span>
              <span className="text-red-600 font-semibold">
                Kritisch: {data.byPriority.critical}
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
