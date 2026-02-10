/**
 * Margin Analyzer Widget
 *
 * Dashboard-Widget fuer Margenanalyse pro Kategorie.
 *
 * Features:
 * - Gestapeltes Balkendiagramm (Umsatz vs. Kosten)
 * - Marge-% Linie als Overlay
 * - Gesamt-KPI (Gesamtmarge, Marge-%)
 * - Deutsche Beschriftung
 *
 * Phase C: Business KPIs
 */

import { useMemo } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import {
  PieChart,
  AlertTriangle,
  RefreshCw,
  TrendingUp,
} from 'lucide-react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';
import { useTheme } from '@/lib/theme/ThemeContext';
import { useMarginAnalyzer } from '../../hooks/useMarginAnalyzer';

/**
 * Formatiere Waehrung (EUR)
 */
function formatCurrency(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * Hook fuer Chart-Farben basierend auf Theme
 */
function useChartColors() {
  const { displayMode } = useTheme();

  return useMemo(() => {
    const computedStyle = getComputedStyle(document.documentElement);
    const getColor = (varName: string, fallback: string): string => {
      const value = computedStyle.getPropertyValue(varName).trim();
      return value || fallback;
    };

    return {
      revenue: getColor('--chart-2', 'oklch(0.72 0.17 145)'),
      cost: getColor('--chart-4', 'oklch(0.55 0.22 25)'),
      marginLine: getColor('--chart-1', 'oklch(0.55 0.18 250)'),
    };
  }, [displayMode]);
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; color?: string; unit?: string }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload || !label) return null;

  return (
    <div className="rounded-lg border bg-background p-3 shadow-md">
      <p className="font-medium mb-2">{label}</p>
      {payload.map((entry, index) => (
        <div key={index} className="flex items-center gap-2 text-sm">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-medium">
            {entry.name === 'Marge %'
              ? `${Number(entry.value).toFixed(1)}%`
              : formatCurrency(Number(entry.value))}
          </span>
        </div>
      ))}
    </div>
  );
}

export function MarginAnalyzerWidget() {
  const chartColors = useChartColors();

  useWidgetSubscription('margin-analyzer', {
    debounceMs: 500,
    autoInvalidate: true,
    queryKeysToInvalidate: [['dashboard-widgets', 'margin-analyzer']],
  });

  const { data, isLoading, isError, error, refetch } = useMarginAnalyzer();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-56" />
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 mb-4">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
          <Skeleton className="h-[280px] w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PieChart className="w-5 h-5" />
            Margenanalyse
          </CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Margendaten
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription className="flex items-center justify-between">
              <span>{error?.message || 'Verbindung fehlgeschlagen'}</span>
              <Button variant="ghost" size="sm" onClick={() => refetch()}>
                <RefreshCw className="w-4 h-4 mr-1" />
                Wiederholen
              </Button>
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const marginPositive = data.overallMarginPct >= 0;

  // Chart-Daten aufbereiten
  const chartData = data.dataPoints.map((dp) => ({
    category: dp.category,
    Umsatz: dp.revenue,
    Kosten: dp.cost,
    'Marge %': dp.marginPct,
  }));

  return (
    <ErrorBoundary
      fallback={<DashboardSectionError section="Margenanalyse" />}
      errorTitle="Margen Fehler"
      errorDescription="Die Margenanalyse konnte nicht geladen werden."
    >
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <PieChart className="w-5 h-5" />
                Margenanalyse
              </CardTitle>
              <CardDescription>
                Umsatz vs. Kosten mit Marge pro Kategorie
              </CardDescription>
            </div>
            <Button variant="ghost" size="icon" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* KPI-Zusammenfassung */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="p-3 rounded-lg border bg-muted/30">
              <p className="text-xs text-muted-foreground mb-1">Gesamtmarge</p>
              <p className={`text-xl font-bold ${marginPositive ? 'text-green-600' : 'text-red-600'}`}>
                {formatCurrency(data.overallMargin)}
              </p>
            </div>
            <div className="p-3 rounded-lg border bg-muted/30">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground mb-1">Marge %</p>
                <Badge variant={marginPositive ? 'default' : 'destructive'} className="text-xs">
                  <TrendingUp className="w-3 h-3 mr-1" />
                  {data.overallMarginPct.toFixed(1)}%
                </Badge>
              </div>
              <p className={`text-xl font-bold ${marginPositive ? 'text-green-600' : 'text-red-600'}`}>
                {data.overallMarginPct.toFixed(1)}%
              </p>
            </div>
          </div>

          {/* Chart */}
          <div
            className="h-[280px]"
            role="img"
            aria-label="Margenanalyse Balkendiagramm mit Marge-Linie"
          >
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} barGap={2}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="category"
                  tick={{ fontSize: 11 }}
                  tickMargin={8}
                />
                <YAxis
                  yAxisId="left"
                  tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
                  tick={{ fontSize: 11 }}
                  tickMargin={8}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tickFormatter={(v: number) => `${v}%`}
                  tick={{ fontSize: 11 }}
                  tickMargin={8}
                  domain={[0, 100]}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Bar
                  yAxisId="left"
                  dataKey="Umsatz"
                  fill={chartColors.revenue}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={40}
                />
                <Bar
                  yAxisId="left"
                  dataKey="Kosten"
                  fill={chartColors.cost}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={40}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="Marge %"
                  stroke={chartColors.marginLine}
                  strokeWidth={2}
                  dot={{ r: 4, fill: chartColors.marginLine }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Screen Reader Tabelle */}
          <table className="sr-only" aria-label="Margendaten als Tabelle">
            <caption>Umsatz, Kosten und Marge pro Kategorie</caption>
            <thead>
              <tr>
                <th scope="col">Kategorie</th>
                <th scope="col">Umsatz</th>
                <th scope="col">Kosten</th>
                <th scope="col">Marge</th>
                <th scope="col">Marge %</th>
              </tr>
            </thead>
            <tbody>
              {data.dataPoints.map((dp, index) => (
                <tr key={index}>
                  <td>{dp.category}</td>
                  <td>{formatCurrency(dp.revenue)}</td>
                  <td>{formatCurrency(dp.cost)}</td>
                  <td>{formatCurrency(dp.margin)}</td>
                  <td>{dp.marginPct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </ErrorBoundary>
  );
}
