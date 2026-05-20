/**
 * Trend Sparklines Component
 *
 * Displays mini sparkline charts for key metrics over time.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import type { TrendData, TrendPoint } from '../types';
import { TrendingUp, FileText, Euro, Zap, Bell } from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';

interface TrendSparklinesProps {
  trendData: TrendData;
  days: number;
  onDaysChange: (days: number) => void;
}

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
}

function Sparkline({ data, width = 120, height = 40, className }: SparklineProps) {
  if (!data.length || data.every((v) => v === 0)) {
    return (
      <div
        className={cn('flex items-center justify-center text-muted-foreground', className)}
        style={{ width, height }}
      >
        <span className="text-xs">Keine Daten</span>
      </div>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - min) / range) * height;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg
      width={width}
      height={height}
      className={cn('text-primary', className)}
      aria-label="Trend-Diagramm"
    >
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        points={points}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

interface MetricCardProps {
  icon: React.ElementType;
  label: string;
  currentValue: string | number;
  data: TrendPoint[];
}

function MetricCard({ icon: Icon, label, currentValue, data }: MetricCardProps) {
  const values = data.map((d) => d.value);

  // Calculate trend (last value vs average of previous values)
  const lastValue = values[values.length - 1] || 0;
  const previousAvg =
    values.length > 1
      ? values.slice(0, -1).reduce((a, b) => a + b, 0) / (values.length - 1)
      : 0;
  const trendUp = lastValue >= previousAvg;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Icon className="w-4 h-4 text-muted-foreground" />
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-end justify-between">
          <div>
            <div className="text-2xl font-bold">{currentValue}</div>
            <div
              className={cn(
                'text-xs flex items-center gap-1 mt-1',
                trendUp ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
              )}
            >
              <TrendingUp
                className={cn('w-3 h-3', !trendUp && 'rotate-180')}
              />
              {trendUp ? 'Steigend' : 'Fallend'}
            </div>
          </div>
          <Sparkline data={values} width={100} height={40} />
        </div>
      </CardContent>
    </Card>
  );
}

export function TrendSparklines({ trendData, days, onDaysChange }: TrendSparklinesProps) {
  const [selectedPeriod, setSelectedPeriod] = useState(days);

  const handlePeriodChange = (newDays: number) => {
    setSelectedPeriod(newDays);
    onDaysChange(newDays);
  };

  const periods = [
    { label: '7T', days: 7 },
    { label: '30T', days: 30 },
    { label: '90T', days: 90 },
    { label: '1J', days: 365 },
  ];

  // Get current values (last data point)
  const getCurrentValue = (data: TrendPoint[]) => {
    return data.length > 0 ? data[data.length - 1].value : 0;
  };

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat('de-DE').format(Math.round(num));
  };

  const formatCurrency = (num: number) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num);
  };

  const formatPercentage = (num: number) => {
    return `${Math.round(num * 100)}%`;
  };

  return (
    <div className="space-y-4">
      {/* Period Selector */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Trends</h3>
        <div className="flex gap-1">
          {periods.map((period) => (
            <Button
              key={period.days}
              variant={selectedPeriod === period.days ? 'default' : 'outline'}
              size="sm"
              onClick={() => handlePeriodChange(period.days)}
            >
              {period.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          icon={FileText}
          label="Verarbeitete Dokumente"
          currentValue={formatNumber(getCurrentValue(trendData.documentsProcessed))}
          data={trendData.documentsProcessed}
        />

        <MetricCard
          icon={Euro}
          label="Rechnungsvolumen"
          currentValue={formatCurrency(getCurrentValue(trendData.invoiceVolume))}
          data={trendData.invoiceVolume}
        />

        <MetricCard
          icon={Zap}
          label="Auto-Verarbeitung"
          currentValue={formatPercentage(getCurrentValue(trendData.autoProcessRate))}
          data={trendData.autoProcessRate}
        />

        <MetricCard
          icon={Bell}
          label="Alert-Anzahl"
          currentValue={formatNumber(getCurrentValue(trendData.alertCount))}
          data={trendData.alertCount}
        />
      </div>
    </div>
  );
}
