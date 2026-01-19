/**
 * Usage Chart Component
 *
 * Zeigt die Nutzungsstatistiken als Liniendiagramm.
 */

import { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import type { UsageTimelineItem } from '../hooks/use-tenant-limits';

interface UsageChartProps {
  timeline: UsageTimelineItem[];
  periodType: 'hourly' | 'daily' | 'monthly';
}

export function UsageChart({ timeline, periodType }: UsageChartProps) {
  const chartData = useMemo(() => {
    return timeline.map((item) => ({
      ...item,
      date: formatDate(item.period_start, periodType),
    }));
  }, [timeline, periodType]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Nutzungsverlauf</CardTitle>
        <CardDescription>
          API-Anfragen und verarbeitete Dokumente ({periodType === 'hourly' ? 'stuendlich' : periodType === 'daily' ? 'taeglich' : 'monatlich'})
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => formatNumber(value)}
              />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  return (
                    <div className="rounded-lg border bg-background p-2 shadow-sm">
                      <p className="font-medium">{label}</p>
                      {payload.map((entry, index) => (
                        <p key={index} className="text-sm" style={{ color: entry.color }}>
                          {entry.name}: {formatNumber(entry.value as number)}
                        </p>
                      ))}
                    </div>
                  );
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="total_requests"
                name="Anfragen"
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="rate_limited"
                name="Rate-Limited"
                stroke="hsl(var(--destructive))"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="documents_processed"
                name="Dokumente"
                stroke="hsl(var(--chart-3))"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function formatDate(isoDate: string, periodType: string): string {
  const date = new Date(isoDate);
  if (periodType === 'hourly') {
    return date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  }
  if (periodType === 'monthly') {
    return date.toLocaleDateString('de-DE', { month: 'short', year: '2-digit' });
  }
  return date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
}

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toString();
}
