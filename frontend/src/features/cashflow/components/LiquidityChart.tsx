/**
 * Liquidity Forecast Chart
 *
 * Zeigt die Liquiditätsprognose als Area-Chart mit Warnzonen.
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
  ReferenceArea,
} from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { ForecastDay } from '../api/cashflow-api';

interface LiquidityChartProps {
  forecast: ForecastDay[];
  currency?: string;
}

export function LiquidityChart({ forecast, currency = 'EUR' }: LiquidityChartProps) {
  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
  };

  // Find warning zones
  const warningZones = useMemo(() => {
    const zones: { start: string; end: string; type: 'warning' | 'critical' }[] = [];
    let currentZone: { start: string; type: 'warning' | 'critical' } | null = null;

    // for-of statt forEach, damit TypeScript die currentZone-Zuweisungen
    // im Kontrollfluss verfolgen kann (sonst TS2698 beim Spread)
    for (const [index, day] of forecast.entries()) {
      const type = day.is_critical ? 'critical' : day.is_warning ? 'warning' : null;

      if (type && !currentZone) {
        currentZone = { start: day.date, type };
      } else if (!type && currentZone) {
        zones.push({ ...currentZone, end: forecast[index - 1].date });
        currentZone = null;
      } else if (type && currentZone && type !== currentZone.type) {
        zones.push({ ...currentZone, end: forecast[index - 1].date });
        currentZone = { start: day.date, type };
      }
    }

    if (currentZone) {
      zones.push({ ...currentZone, end: forecast[forecast.length - 1].date });
    }

    return zones;
  }, [forecast]);

  const minBalance = Math.min(...forecast.map((f) => f.balance));
  const maxBalance = Math.max(...forecast.map((f) => f.balance));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Liquiditätsprognose</CardTitle>
        <CardDescription>
          Voraussichtlicher Kontostand für die nächsten {forecast.length} Tage
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-[350px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={forecast}
              margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
            >
              <defs>
                <linearGradient id="balanceGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--chart-1))" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="hsl(var(--chart-1))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                tick={{ fontSize: 11 }}
                interval="preserveStartEnd"
              />
              <YAxis
                tickFormatter={(v) => formatCurrency(v)}
                tick={{ fontSize: 11 }}
                domain={[Math.min(0, minBalance * 1.1), maxBalance * 1.1]}
              />
              <Tooltip
                formatter={(value: number, name: string) => [
                  formatCurrency(value),
                  name === 'balance'
                    ? 'Kontostand'
                    : name === 'inflows'
                    ? 'Eingänge'
                    : 'Ausgänge',
                ]}
                labelFormatter={(label) => new Date(label).toLocaleDateString('de-DE')}
              />

              {/* Warning zones */}
              {warningZones.map((zone, index) => (
                <ReferenceArea
                  key={index}
                  x1={zone.start}
                  x2={zone.end}
                  y1={minBalance * 1.1}
                  y2={0}
                  fill={zone.type === 'critical' ? 'hsl(0, 72%, 51%)' : 'hsl(38, 92%, 50%)'}
                  fillOpacity={0.1}
                />
              ))}

              {/* Zero line */}
              <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />

              <Area
                type="monotone"
                dataKey="balance"
                stroke="hsl(var(--chart-1))"
                fill="url(#balanceGradient)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
