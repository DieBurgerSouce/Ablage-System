/**
 * Trend Chart Component
 *
 * Visualisiert die Trend-Analyse über mehrere Quartale.
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';
import type { TrendAnalysis } from '../api/risk-intelligence-api';

interface TrendChartProps {
  trend: TrendAnalysis;
  className?: string;
}

export function TrendChart({ trend, className }: TrendChartProps) {
  const getTrendIcon = () => {
    switch (trend.direction) {
      case 'improving':
        return <TrendingDown className="w-4 h-4 text-green-500" />;
      case 'stable':
        return <Minus className="w-4 h-4 text-blue-500" />;
      case 'deteriorating':
        return <TrendingUp className="w-4 h-4 text-orange-500" />;
      case 'critical':
        return <AlertTriangle className="w-4 h-4 text-red-500" />;
    }
  };

  const getTrendBadge = () => {
    const variants: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; label: string }> = {
      improving: { variant: 'default', label: 'Verbessernd' },
      stable: { variant: 'secondary', label: 'Stabil' },
      deteriorating: { variant: 'outline', label: 'Verschlechternd' },
      critical: { variant: 'destructive', label: 'Kritisch' },
    };
    const { variant, label } = variants[trend.direction] || variants.stable;
    return (
      <Badge variant={variant} className="gap-1">
        {getTrendIcon()}
        {label}
      </Badge>
    );
  };

  const chartData = trend.quarters.map((q) => ({
    quarter: q.quarter,
    delay: q.avg_payment_delay,
    defaultRate: q.default_rate * 100,
    invoices: q.invoice_count,
  }));

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg">Trend-Analyse</CardTitle>
            <CardDescription>
              Entwicklung über {trend.quarters.length} Quartale
            </CardDescription>
          </div>
          {getTrendBadge()}
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="text-center p-3 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground">Veränderung</p>
            <p className={`text-xl font-bold ${trend.change_percentage > 0 ? 'text-red-500' : 'text-green-500'}`}>
              {trend.change_percentage > 0 ? '+' : ''}{trend.change_percentage.toFixed(1)}%
            </p>
          </div>
          <div className="text-center p-3 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground">Trend-Score</p>
            <p className="text-xl font-bold">{trend.trend_score.toFixed(0)}</p>
          </div>
        </div>

        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="quarter"
                tick={{ fontSize: 12 }}
                className="text-muted-foreground"
              />
              <YAxis
                yAxisId="left"
                tick={{ fontSize: 12 }}
                className="text-muted-foreground"
                label={{
                  value: 'Tage',
                  angle: -90,
                  position: 'insideLeft',
                  className: 'fill-muted-foreground',
                }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 12 }}
                className="text-muted-foreground"
                label={{
                  value: '%',
                  angle: 90,
                  position: 'insideRight',
                  className: 'fill-muted-foreground',
                }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px',
                }}
                labelStyle={{ color: 'hsl(var(--foreground))' }}
              />
              <ReferenceLine
                yAxisId="left"
                y={30}
                stroke="#f59e0b"
                strokeDasharray="3 3"
                label={{ value: 'Ziel', position: 'right', fill: '#f59e0b', fontSize: 10 }}
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="delay"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={{ fill: '#3b82f6' }}
                name="Zahlungsverzögerung (Tage)"
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="defaultRate"
                stroke="#ef4444"
                strokeWidth={2}
                dot={{ fill: '#ef4444' }}
                name="Ausfallrate (%)"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="flex justify-center gap-6 mt-2 text-xs">
          <div className="flex items-center gap-1">
            <div className="w-3 h-0.5 bg-blue-500" />
            <span className="text-muted-foreground">Verzögerung</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-0.5 bg-red-500" />
            <span className="text-muted-foreground">Ausfallrate</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
