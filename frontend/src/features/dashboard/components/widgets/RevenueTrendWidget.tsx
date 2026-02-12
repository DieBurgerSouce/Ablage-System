/**
 * Revenue Trend Widget
 *
 * Dashboard-Widget für Umsatzentwicklung nach Kategorie und Monat.
 *
 * Features:
 * - Balkendiagramm Umsatz vs. Ausgaben
 * - Vergleichszeitraum-Overlay (Vorperiode / Vorjahr)
 * - KPI-Zusammenfassung (Gesamtumsatz, Ausgaben, Nettoeinkommen)
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
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';
import { useTheme } from '@/lib/theme/ThemeContext';
import { useRevenueTrend, formatCurrency, formatPercent } from '../../hooks/useRevenueTrend';

/**
 * Hook für Chart-Farben basierend auf Theme
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
      expense: getColor('--chart-4', 'oklch(0.55 0.22 25)'),
      revenuePrev: getColor('--chart-3', 'oklch(0.65 0.10 145)'),
      expensePrev: getColor('--chart-5', 'oklch(0.50 0.12 25)'),
    };
  }, [displayMode]);
}

/**
 * Formatiere Monat (kurz, deutsch)
 */
function formatPeriodLabel(period: string): string {
  // Erwarte ISO-Datum oder Monatsformat "2026-01"
  if (period.length <= 7) {
    const [year, month] = period.split('-');
    const months = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
    const idx = parseInt(month, 10) - 1;
    if (idx >= 0 && idx < 12) {
      return `${months[idx]} ${year.slice(2)}`;
    }
  }
  return period;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; color?: string }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload || !label) return null;

  return (
    <div className="rounded-lg border bg-background p-3 shadow-md">
      <p className="font-medium mb-2">{formatPeriodLabel(String(label))}</p>
      {payload.map((entry, index) => (
        <div key={index} className="flex items-center gap-2 text-sm">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-medium">{formatCurrency(Number(entry.value))}</span>
        </div>
      ))}
    </div>
  );
}

export function RevenueTrendWidget() {
  const chartColors = useChartColors();

  useWidgetSubscription('revenue-trend', {
    debounceMs: 500,
    autoInvalidate: true,
    queryKeysToInvalidate: [['dashboard-widgets', 'revenue-trend']],
  });

  const { data, isLoading, isError, error, refetch } = useRevenueTrend();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <Skeleton className="h-16" />
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
            <BarChart3 className="w-5 h-5" />
            Umsatzentwicklung
          </CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Umsatzdaten
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

  const hasComparison = data.comparison !== undefined && data.comparison !== null;
  const netPositive = data.netIncome >= 0;

  // Chart-Daten aufbereiten
  const chartData = data.dataPoints.map((dp) => ({
    period: dp.period,
    Umsatz: dp.revenue,
    Ausgaben: dp.expense,
  }));

  return (
    <ErrorBoundary
      fallback={<DashboardSectionError section="Umsatzentwicklung" />}
      errorTitle="Umsatz Fehler"
      errorDescription="Die Umsatzentwicklung konnte nicht geladen werden."
    >
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="w-5 h-5" />
                Umsatzentwicklung
              </CardTitle>
              <CardDescription>
                {data.dateFrom && data.dateTo
                  ? `${new Date(data.dateFrom).toLocaleDateString('de-DE')} - ${new Date(data.dateTo).toLocaleDateString('de-DE')}`
                  : 'Gesamter Zeitraum'}
              </CardDescription>
            </div>
            <Button variant="ghost" size="icon" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* KPI-Zusammenfassung */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="p-3 rounded-lg border bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800">
              <p className="text-xs text-muted-foreground mb-1">Umsatz</p>
              <p className="text-lg font-bold text-green-600">
                {formatCurrency(data.totalRevenue)}
              </p>
              {hasComparison && data.comparison && (
                <div className="flex items-center gap-1 mt-1">
                  {data.comparison.revenueChangePct >= 0 ? (
                    <TrendingUp className="w-3 h-3 text-green-600" />
                  ) : (
                    <TrendingDown className="w-3 h-3 text-red-600" />
                  )}
                  <span className="text-xs text-muted-foreground">
                    {formatPercent(data.comparison.revenueChangePct)}
                  </span>
                </div>
              )}
            </div>

            <div className="p-3 rounded-lg border bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800">
              <p className="text-xs text-muted-foreground mb-1">Ausgaben</p>
              <p className="text-lg font-bold text-red-600">
                {formatCurrency(data.totalExpenses)}
              </p>
              {hasComparison && data.comparison && (
                <div className="flex items-center gap-1 mt-1">
                  {data.comparison.expenseChangePct <= 0 ? (
                    <TrendingDown className="w-3 h-3 text-green-600" />
                  ) : (
                    <TrendingUp className="w-3 h-3 text-red-600" />
                  )}
                  <span className="text-xs text-muted-foreground">
                    {formatPercent(data.comparison.expenseChangePct)}
                  </span>
                </div>
              )}
            </div>

            <div className="p-3 rounded-lg border bg-muted/30">
              <p className="text-xs text-muted-foreground mb-1">Netto</p>
              <p className={`text-lg font-bold ${netPositive ? 'text-green-600' : 'text-red-600'}`}>
                {formatCurrency(data.netIncome)}
              </p>
              {hasComparison && (
                <Badge variant={netPositive ? 'default' : 'destructive'} className="text-xs mt-1">
                  {netPositive ? 'Gewinn' : 'Verlust'}
                </Badge>
              )}
            </div>
          </div>

          {/* Chart */}
          <div
            className="h-[280px]"
            role="img"
            aria-label="Umsatz vs. Ausgaben Balkendiagramm"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} barGap={2}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="period"
                  tickFormatter={formatPeriodLabel}
                  tick={{ fontSize: 11 }}
                  tickMargin={8}
                />
                <YAxis
                  tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
                  tick={{ fontSize: 11 }}
                  tickMargin={8}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Bar
                  dataKey="Umsatz"
                  fill={chartColors.revenue}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={40}
                />
                <Bar
                  dataKey="Ausgaben"
                  fill={chartColors.expense}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={40}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Screen Reader Tabelle */}
          <table className="sr-only" aria-label="Umsatzdaten als Tabelle">
            <caption>Monatliche Umsätze und Ausgaben</caption>
            <thead>
              <tr>
                <th scope="col">Zeitraum</th>
                <th scope="col">Umsatz</th>
                <th scope="col">Ausgaben</th>
                <th scope="col">Netto</th>
              </tr>
            </thead>
            <tbody>
              {data.dataPoints.map((dp, index) => (
                <tr key={index}>
                  <td>{formatPeriodLabel(dp.period)}</td>
                  <td>{formatCurrency(dp.revenue)}</td>
                  <td>{formatCurrency(dp.expense)}</td>
                  <td>{formatCurrency(dp.net)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </ErrorBoundary>
  );
}
