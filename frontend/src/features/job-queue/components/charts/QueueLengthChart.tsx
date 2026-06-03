/**
 * QueueLengthChart
 *
 * Bar Chart zeigt die aktuelle Länge aller Queues.
 */

import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Layers } from 'lucide-react';
import {
  QUEUE_UTILIZATION_THRESHOLDS,
  QUEUE_UTILIZATION_PERCENT_THRESHOLDS,
  getQueueBarColor,
} from '../../constants/thresholds';

// ==================== Types ====================

interface QueueData {
  name: string;
  displayName: string;
  length: number;
  processing: number;
  maxCapacity?: number;
}

interface QueueLengthChartProps {
  data?: QueueData[];
  isLoading?: boolean;
  title?: string;
  description?: string;
  warningThreshold?: number;
  criticalThreshold?: number;
  height?: number;
}

// ==================== Color Helper ====================
// Nutzt zentrale getQueueBarColor aus constants/thresholds.ts

// ==================== Custom Tooltip ====================

interface TooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: QueueData;
  }>;
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || !payload.length) return null;

  const data = payload[0].payload;
  const utilizationPercent = data.maxCapacity
    ? Math.round((data.length / data.maxCapacity) * 100)
    : null;

  return (
    <div className="bg-popover border rounded-lg shadow-lg p-3">
      <p className="font-medium text-sm mb-2">{data.displayName}</p>
      <div className="space-y-1 text-sm">
        <div className="flex items-center justify-between gap-4">
          <span className="text-muted-foreground">Wartend:</span>
          <span className="font-medium">{data.length}</span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="text-muted-foreground">In Bearbeitung:</span>
          <span className="font-medium">{data.processing}</span>
        </div>
        {utilizationPercent !== null && (
          <div className="flex items-center justify-between gap-4">
            <span className="text-muted-foreground">Auslastung:</span>
            <span className={`font-medium ${
              utilizationPercent >= QUEUE_UTILIZATION_PERCENT_THRESHOLDS.CRITICAL ? 'text-red-600' :
              utilizationPercent >= QUEUE_UTILIZATION_PERCENT_THRESHOLDS.WARNING ? 'text-yellow-600' : 'text-green-600'
            }`}>
              {utilizationPercent}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ==================== Component ====================

export function QueueLengthChart({
  data,
  isLoading = false,
  title = 'Queue-Auslastung',
  description = 'Aktuelle Länge der Warteschlangen',
  warningThreshold = QUEUE_UTILIZATION_THRESHOLDS.WARNING,
  criticalThreshold = QUEUE_UTILIZATION_THRESHOLDS.CRITICAL,
  height = 250,
}: QueueLengthChartProps) {
  const chartData = useMemo(() => {
    return data ?? [];
  }, [data]);

  // Calculate totals
  const totals = useMemo(() => {
    return chartData.reduce(
      (acc, queue) => ({
        length: acc.length + queue.length,
        processing: acc.processing + queue.processing,
      }),
      { length: 0, processing: 0 }
    );
  }, [chartData]);

  // Determine overall status
  const overallStatus = useMemo(() => {
    const maxLength = Math.max(...chartData.map(q => q.length));
    if (maxLength >= criticalThreshold) return { label: 'Kritisch', variant: 'destructive' as const };
    if (maxLength >= warningThreshold) return { label: 'Erhöht', variant: 'secondary' as const };
    return { label: 'Normal', variant: 'default' as const };
  }, [chartData, warningThreshold, criticalThreshold]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-60" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[250px] w-full" />
        </CardContent>
      </Card>
    );
  }

  if (chartData.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Layers className="h-4 w-4 text-muted-foreground" />
            {title}
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <div
            className="flex items-center justify-center text-sm text-muted-foreground"
            style={{ height }}
          >
            Keine Daten für den gewählten Zeitraum
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Layers className="h-4 w-4 text-muted-foreground" />
              {title}
            </CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold">{totals.length}</div>
            <div className="flex items-center gap-2 justify-end mt-1">
              <span className="text-xs text-muted-foreground">{totals.processing} aktiv</span>
              <Badge variant={overallStatus.variant}>{overallStatus.label}</Badge>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart
            data={chartData}
            margin={{ top: 10, right: 30, left: 0, bottom: 5 }}
            layout="vertical"
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              className="text-muted-foreground"
            />
            <YAxis
              type="category"
              dataKey="displayName"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={80}
              className="text-muted-foreground"
            />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="length" radius={[0, 4, 4, 0]} maxBarSize={30}>
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={getQueueBarColor(entry.length)}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        {/* Legend */}
        <div className="flex items-center justify-center gap-4 mt-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-sm bg-green-500" />
            <span>Normal</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-sm bg-yellow-500" />
            <span>Erhöht ({warningThreshold}+)</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-sm bg-red-500" />
            <span>Kritisch ({criticalThreshold}+)</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default QueueLengthChart;
