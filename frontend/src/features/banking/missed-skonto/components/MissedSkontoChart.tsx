/**
 * Missed Skonto Chart
 * Chart für monatliche Skonto-Nutzung
 */

import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import type { MonthlySkontoSummary } from '../types';

interface MissedSkontoChartProps {
  data?: MonthlySkontoSummary[];
  isLoading?: boolean;
}

// Monatsnamen auf Deutsch
const MONTH_NAMES = [
  'Jan', 'Feb', 'Maer', 'Apr', 'Mai', 'Jun',
  'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez',
];

export function MissedSkontoChart({ data = [], isLoading }: MissedSkontoChartProps) {
  const chartData = useMemo(() => {
    if (!data.length) return [];

    return data.map((item) => ({
      name: `${MONTH_NAMES[parseInt(item.month, 10) - 1] || item.month} ${item.year}`,
      genutzt: item.usedAmount,
      verpasst: item.missedAmount,
      rate: item.usageRate,
    }));
  }, [data]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[300px] w-full" />
        </CardContent>
      </Card>
    );
  }

  if (chartData.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Monatliche Skonto-Übersicht</CardTitle>
          <CardDescription>
            Vergleich von genutzten und verpassten Skonto-Möglichkeiten
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[300px] text-muted-foreground">
            Keine Daten verfügbar
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Monatliche Skonto-Übersicht</CardTitle>
        <CardDescription>
          Vergleich von genutzten und verpassten Skonto-Möglichkeiten
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tickFormatter={(value) =>
                new Intl.NumberFormat('de-DE', {
                  style: 'currency',
                  currency: 'EUR',
                  notation: 'compact',
                }).format(value)
              }
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              formatter={(value: number, name: string) => [
                new Intl.NumberFormat('de-DE', {
                  style: 'currency',
                  currency: 'EUR',
                }).format(value),
                name === 'genutzt' ? 'Genutzt' : 'Verpasst',
              ]}
              labelFormatter={(label) => `Monat: ${label}`}
              contentStyle={{
                backgroundColor: 'hsl(var(--background))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '6px',
              }}
            />
            <Legend
              formatter={(value) => (value === 'genutzt' ? 'Genutzt' : 'Verpasst')}
            />
            <Bar
              dataKey="genutzt"
              fill="hsl(142, 76%, 36%)"
              name="genutzt"
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="verpasst"
              fill="hsl(0, 84%, 60%)"
              name="verpasst"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
