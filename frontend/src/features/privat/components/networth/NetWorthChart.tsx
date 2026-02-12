/**
 * NetWorthChart - Nettovermögen-Verlauf
 *
 * Zeigt die Entwicklung des Nettovermögens über Zeit:
 * - Line Chart mit 12 Monaten
 * - Vermögen vs. Verbindlichkeiten Vergleich
 * - Trend-Indikator
 */

import * as React from 'react';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from 'recharts';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import type { NetWorthHistoryEntry } from '../../hooks/useNetWorth';
import { formatCurrencyDE, abbreviateNumber } from '../../hooks/useNetWorth';

// ==================== Types ====================

interface NetWorthChartProps {
  history: NetWorthHistoryEntry[];
  isLoading?: boolean;
  className?: string;
}

type ChartView = 'networth' | 'comparison' | 'bars';

// ==================== Loading Skeleton ====================

function LoadingSkeleton() {
  return (
    <Card>
      <CardHeader>
        <div className="h-5 w-48 bg-muted animate-pulse rounded" />
        <div className="h-4 w-64 bg-muted animate-pulse rounded mt-1" />
      </CardHeader>
      <CardContent>
        <div className="h-64 w-full bg-muted animate-pulse rounded" />
      </CardContent>
    </Card>
  );
}

// ==================== Custom Tooltip ====================

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    name: string;
    value: number;
    color: string;
    dataKey: string;
  }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="bg-background border rounded-lg shadow-lg p-3 min-w-[180px]">
      <p className="font-medium text-sm mb-2">{label}</p>
      <div className="space-y-1">
        {payload.map((entry, index) => (
          <div key={index} className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              <span className="text-xs text-muted-foreground">
                {entry.dataKey === 'netWorth'
                  ? 'Nettovermögen'
                  : entry.dataKey === 'totalAssets'
                    ? 'Vermögen'
                    : 'Verbindlichkeiten'}
              </span>
            </div>
            <span className="text-xs font-medium">
              {formatCurrencyDE(entry.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ==================== Chart Components ====================

interface ChartDataPoint {
  date: string;
  displayDate: string;
  netWorth: number;
  totalAssets: number;
  totalLiabilities: number;
}

function prepareChartData(history: NetWorthHistoryEntry[]): ChartDataPoint[] {
  return history.map((entry) => {
    const date = new Date(entry.date);
    return {
      date: entry.date,
      displayDate: date.toLocaleDateString('de-DE', {
        month: 'short',
        year: '2-digit',
      }),
      netWorth: entry.netWorth,
      totalAssets: entry.totalAssets,
      totalLiabilities: entry.totalLiabilities,
    };
  });
}

function NetWorthLineChart({ data }: { data: ChartDataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="netWorthGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis
          dataKey="displayDate"
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(value) => abbreviateNumber(value)}
          width={70}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="3 3" />
        <Area
          type="monotone"
          dataKey="netWorth"
          stroke="#3b82f6"
          fill="url(#netWorthGradient)"
          strokeWidth={2}
          dot={{ fill: '#3b82f6', strokeWidth: 0, r: 3 }}
          activeDot={{ r: 5, fill: '#3b82f6' }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function ComparisonChart({ data }: { data: ChartDataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis
          dataKey="displayDate"
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(value) => abbreviateNumber(value)}
          width={70}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ paddingTop: '10px' }}
          formatter={(value) =>
            value === 'totalAssets'
              ? 'Vermögen'
              : value === 'totalLiabilities'
                ? 'Verbindlichkeiten'
                : 'Nettovermögen'
          }
        />
        <Line
          type="monotone"
          dataKey="totalAssets"
          stroke="#22c55e"
          strokeWidth={2}
          dot={{ fill: '#22c55e', strokeWidth: 0, r: 3 }}
        />
        <Line
          type="monotone"
          dataKey="totalLiabilities"
          stroke="#ef4444"
          strokeWidth={2}
          dot={{ fill: '#ef4444', strokeWidth: 0, r: 3 }}
        />
        <Line
          type="monotone"
          dataKey="netWorth"
          stroke="#3b82f6"
          strokeWidth={2}
          strokeDasharray="5 5"
          dot={{ fill: '#3b82f6', strokeWidth: 0, r: 3 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function AssetsVsLiabilitiesBarChart({ data }: { data: ChartDataPoint[] }) {
  // Take only last 6 months for bar chart
  const recentData = data.slice(-6);

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart
        data={recentData}
        margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
      >
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis
          dataKey="displayDate"
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(value) => abbreviateNumber(value)}
          width={70}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ paddingTop: '10px' }}
          formatter={(value) =>
            value === 'totalAssets' ? 'Vermögen' : 'Verbindlichkeiten'
          }
        />
        <Bar dataKey="totalAssets" fill="#22c55e" radius={[4, 4, 0, 0]} />
        <Bar dataKey="totalLiabilities" fill="#ef4444" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ==================== Main Component ====================

export function NetWorthLineChartCard({
  history,
  isLoading = false,
  className,
}: NetWorthChartProps) {
  const [chartView, setChartView] = React.useState<ChartView>('networth');

  if (isLoading) {
    return <LoadingSkeleton />;
  }

  if (history.length < 2) {
    return (
      <Card className={cn('', className)}>
        <CardHeader>
          <CardTitle>Nettovermögen-Entwicklung</CardTitle>
          <CardDescription>Historische Entwicklung Ihres Vermögens</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-64 flex items-center justify-center text-muted-foreground">
            <p className="text-center">
              Nicht genügend historische Daten für die Trend-Anzeige.
              <br />
              <span className="text-sm">
                Mindestens 2 Snapshots erforderlich.
              </span>
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const chartData = prepareChartData(history);

  return (
    <Card className={cn('', className)}>
      <CardHeader>
        <CardTitle>Nettovermögen-Entwicklung</CardTitle>
        <CardDescription>
          Historische Entwicklung Ihres Vermögens (letzte 12 Monate)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs
          value={chartView}
          onValueChange={(v) => setChartView(v as ChartView)}
        >
          <TabsList className="grid w-full grid-cols-3 mb-4">
            <TabsTrigger value="networth">Netto</TabsTrigger>
            <TabsTrigger value="comparison">Vergleich</TabsTrigger>
            <TabsTrigger value="bars">Balken</TabsTrigger>
          </TabsList>

          <TabsContent value="networth" className="mt-0">
            <NetWorthLineChart data={chartData} />
          </TabsContent>

          <TabsContent value="comparison" className="mt-0">
            <ComparisonChart data={chartData} />
          </TabsContent>

          <TabsContent value="bars" className="mt-0">
            <AssetsVsLiabilitiesBarChart data={chartData} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

export { NetWorthLineChartCard as NetWorthChart };
export default NetWorthLineChartCard;
