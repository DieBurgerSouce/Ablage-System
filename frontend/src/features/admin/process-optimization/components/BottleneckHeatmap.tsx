/**
 * Bottleneck Heatmap Component
 *
 * Visualisiert Bottlenecks nach Wochentag und Stunde.
 */

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useBottleneckHeatmap } from '../hooks/useProcessMining';

const DAYS = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

function getColorIntensity(value: number, maxValue: number): string {
  if (maxValue === 0 || value === 0) return 'bg-muted/20';

  const ratio = value / maxValue;

  if (ratio >= 0.8) return 'bg-red-500';
  if (ratio >= 0.6) return 'bg-orange-500';
  if (ratio >= 0.4) return 'bg-yellow-500';
  if (ratio >= 0.2) return 'bg-green-400';
  return 'bg-green-200';
}

export function BottleneckHeatmap() {
  const { data, isLoading, error } = useBottleneckHeatmap(7);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64 mt-1" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Lastverteilung</CardTitle>
          <CardDescription>Fehler beim Laden der Heatmap-Daten</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            Keine Daten verfügbar
          </div>
        </CardContent>
      </Card>
    );
  }

  // Create a matrix for easy access
  const matrix: Record<number, Record<number, { count: number; avg_duration_ms: number }>> = {};
  let maxCount = 0;

  for (const item of data.data) {
    if (!matrix[item.day]) {
      matrix[item.day] = {};
    }
    matrix[item.day][item.hour] = {
      count: item.count,
      avg_duration_ms: item.avg_duration_ms,
    };
    maxCount = Math.max(maxCount, item.count);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Lastverteilung
        </CardTitle>
        <CardDescription>
          Dokumenten-Aktivität nach Wochentag und Uhrzeit (letzte {data.period_days} Tage)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <div className="min-w-[600px]">
            {/* Hours Header */}
            <div className="flex ml-8">
              {HOURS.filter((h) => h % 3 === 0).map((hour) => (
                <div
                  key={hour}
                  className="flex-1 text-xs text-muted-foreground text-center"
                  style={{ width: 'calc(100% / 8)' }}
                >
                  {hour}:00
                </div>
              ))}
            </div>

            {/* Heatmap Grid */}
            <div className="space-y-1 mt-2">
              {DAYS.map((day, dayIndex) => (
                <div key={day} className="flex items-center gap-1">
                  <div className="w-8 text-xs text-muted-foreground">{day}</div>
                  <div className="flex-1 flex gap-[2px]">
                    {HOURS.map((hour) => {
                      const cellData = matrix[dayIndex]?.[hour] || {
                        count: 0,
                        avg_duration_ms: 0,
                      };

                      return (
                        <div
                          key={hour}
                          className={`flex-1 h-6 rounded-sm ${getColorIntensity(
                            cellData.count,
                            maxCount
                          )} transition-all hover:ring-2 hover:ring-primary cursor-pointer`}
                          title={`${DAYS[dayIndex]} ${hour}:00-${hour + 1}:00\n${cellData.count} Events\n${
                            cellData.avg_duration_ms > 0
                              ? `Durchschnitt: ${(cellData.avg_duration_ms / 1000).toFixed(1)}s`
                              : ''
                          }`}
                        />
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            {/* Legend */}
            <div className="flex items-center justify-end gap-2 mt-4 text-xs text-muted-foreground">
              <span>Weniger</span>
              <div className="flex gap-1">
                <div className="w-4 h-4 rounded-sm bg-muted/20" />
                <div className="w-4 h-4 rounded-sm bg-green-200" />
                <div className="w-4 h-4 rounded-sm bg-green-400" />
                <div className="w-4 h-4 rounded-sm bg-yellow-500" />
                <div className="w-4 h-4 rounded-sm bg-orange-500" />
                <div className="w-4 h-4 rounded-sm bg-red-500" />
              </div>
              <span>Mehr</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
