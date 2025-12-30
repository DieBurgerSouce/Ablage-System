/**
 * SuccessRateChart
 *
 * Area Chart zeigt die Erfolgsrate über die letzten 24 Stunden.
 * Grün für hohe Rate, Rot/Gelb für niedrige Rate.
 */

import { useMemo } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2 } from 'lucide-react';
import { SUCCESS_RATE_THRESHOLDS } from '../../constants/thresholds';

// ==================== Types ====================

interface SuccessRateDataPoint {
  hour: string;
  timestamp: string;
  successRate: number;
  completed: number;
  total: number;
}

interface SuccessRateChartProps {
  data?: SuccessRateDataPoint[];
  isLoading?: boolean;
  title?: string;
  description?: string;
  targetRate?: number;
  height?: number;
}

// ==================== Mock Data Generator ====================

function generateMockData(): SuccessRateDataPoint[] {
  const data: SuccessRateDataPoint[] = [];
  const now = new Date();

  for (let i = 23; i >= 0; i--) {
    const date = new Date(now);
    date.setHours(date.getHours() - i);

    // Generate varying success rates (80-100%)
    const baseRate = 85 + Math.random() * 15;
    const variance = (Math.random() - 0.5) * 10;
    const successRate = Math.max(70, Math.min(100, baseRate + variance));

    const total = Math.floor(Math.random() * 50) + 20;
    const completed = Math.floor(total * (successRate / 100));

    data.push({
      hour: date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }),
      timestamp: date.toISOString(),
      successRate: Math.round(successRate * 10) / 10,
      completed,
      total,
    });
  }

  return data;
}

// ==================== Custom Tooltip ====================

interface TooltipProps {
  active?: boolean;
  payload?: Array<{
    value: number;
    payload: SuccessRateDataPoint;
  }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload || !payload.length) return null;

  const data = payload[0].payload;

  return (
    <div className="bg-popover border rounded-lg shadow-lg p-3">
      <p className="font-medium text-sm mb-2">{label}</p>
      <div className="space-y-1 text-sm">
        <div className="flex items-center justify-between gap-4">
          <span className="text-muted-foreground">Erfolgsrate:</span>
          <span className={`font-medium ${
            data.successRate >= SUCCESS_RATE_THRESHOLDS.EXCELLENT ? 'text-green-600' :
            data.successRate >= SUCCESS_RATE_THRESHOLDS.GOOD ? 'text-yellow-600' : 'text-red-600'
          }`}>
            {data.successRate}%
          </span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="text-muted-foreground">Erfolgreich:</span>
          <span className="font-medium">{data.completed} / {data.total}</span>
        </div>
      </div>
    </div>
  );
}

// ==================== Component ====================

export function SuccessRateChart({
  data,
  isLoading = false,
  title = 'Erfolgsrate (24h)',
  description = 'Prozentsatz erfolgreich abgeschlossener Jobs',
  targetRate = 95,
  height = 250,
}: SuccessRateChartProps) {
  // Use mock data if no data provided
  const chartData = useMemo(() => {
    return data || generateMockData();
  }, [data]);

  // Calculate average success rate
  const averageRate = useMemo(() => {
    if (chartData.length === 0) return 0;
    const sum = chartData.reduce((acc, point) => acc + point.successRate, 0);
    return Math.round((sum / chartData.length) * 10) / 10;
  }, [chartData]);

  // Determine status based on average rate
  const status = useMemo(() => {
    if (averageRate >= SUCCESS_RATE_THRESHOLDS.EXCELLENT) return { label: 'Ausgezeichnet', variant: 'default' as const, color: 'text-green-600' };
    if (averageRate >= SUCCESS_RATE_THRESHOLDS.GOOD) return { label: 'Gut', variant: 'secondary' as const, color: 'text-yellow-600' };
    return { label: 'Kritisch', variant: 'destructive' as const, color: 'text-red-600' };
  }, [averageRate]);

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

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
              {title}
            </CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <div className="text-right">
            <div className={`text-2xl font-bold ${status.color}`}>{averageRate}%</div>
            <Badge variant={status.variant} className="mt-1">
              {status.label}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart
            data={chartData}
            margin={{ top: 10, right: 30, left: 0, bottom: 5 }}
          >
            <defs>
              <linearGradient id="successRateGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="hour"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              className="text-muted-foreground"
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `${value}%`}
              className="text-muted-foreground"
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine
              y={targetRate}
              stroke="#eab308"
              strokeDasharray="5 5"
              label={{
                value: `Ziel: ${targetRate}%`,
                position: 'right',
                fontSize: 11,
                fill: '#eab308',
              }}
            />
            <Area
              type="monotone"
              dataKey="successRate"
              stroke="#22c55e"
              strokeWidth={2}
              fill="url(#successRateGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export default SuccessRateChart;
