/**
 * Quality Trend Chart Component
 *
 * Displays quality score trend over time.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { QualityTrend } from '../types/data-quality-types';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { TrendingUp } from 'lucide-react';
import { getQualityScoreColor } from '../types/data-quality-types';

interface QualityTrendChartProps {
  data: QualityTrend;
}

export function QualityTrendChart({ data }: QualityTrendChartProps) {
  // Transform data for recharts
  const chartData = data.trend.map((point) => ({
    date: point.date.toLocaleDateString('de-DE', {
      day: '2-digit',
      month: 'short',
    }),
    score: Math.round(point.score),
  }));

  // Calculate average score for color
  const avgScore =
    data.trend.reduce((sum, point) => sum + point.score, 0) / data.trend.length;
  const colors = getQualityScoreColor(avgScore);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="w-5 h-5" />
          Qualitätstrend
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="date"
              className="text-xs"
              tick={{ fill: 'currentColor' }}
            />
            <YAxis
              domain={[0, 100]}
              className="text-xs"
              tick={{ fill: 'currentColor' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
              }}
              labelStyle={{ color: 'hsl(var(--foreground))' }}
            />
            <Line
              type="monotone"
              dataKey="score"
              stroke={
                avgScore >= 70
                  ? 'hsl(142, 76%, 36%)'
                  : avgScore >= 40
                    ? 'hsl(38, 92%, 50%)'
                    : 'hsl(0, 84%, 60%)'
              }
              strokeWidth={2}
              dot={{ fill: colors.text }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
