/**
 * Cash-Flow Forecast Widget
 *
 * Dashboard-Widget für 30/60/90 Tage Liquiditätsprognose.
 *
 * Features:
 * - Einnahmen vs Ausgaben Chart
 * - Periodenzusammenfassung (30/60/90 Tage)
 * - Skonto-Auswirkungen
 * - Risikowanrungen
 *
 * Phase 7: Dashboard Widgets
 */

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { TrendingDown, AlertTriangle, RefreshCw, Wallet, ArrowUp, ArrowDown } from 'lucide-react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';
import { useTheme } from '@/lib/theme/ThemeContext';
import {
  getCashFlowForecast,
  dashboardWidgetKeys,
  type CashFlowForecastData,
} from '../../api/dashboard-widgets';

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
      income: getColor('--chart-2', 'oklch(0.72 0.17 145)'),
      expenses: getColor('--chart-4', 'oklch(0.55 0.22 25)'),
      balance: getColor('--chart-1', 'oklch(0.55 0.18 250)'),
    };
  }, [displayMode]);
}

/**
 * Formatiere Währung kompakt
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
 * Formatiere Datum kurz (TT.MM)
 */
function formatDateShort(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
  });
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
      <p className="font-medium mb-2">{formatDateShort(String(label))}</p>
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

interface PeriodCardProps {
  title: string;
  income: number;
  expenses: number;
  netFlow: number;
  endingBalance: number;
  isActive: boolean;
  onClick: () => void;
}

function PeriodCard({
  title,
  income,
  expenses,
  netFlow,
  endingBalance,
  isActive,
  onClick,
}: PeriodCardProps) {
  const isPositive = netFlow >= 0;

  return (
    <button
      onClick={onClick}
      className={`
        flex-1 p-3 rounded-lg border text-left transition-all
        ${isActive
          ? 'border-primary bg-primary/5 ring-1 ring-primary'
          : 'border-border hover:border-primary/50'
        }
      `}
    >
      <p className="text-xs text-muted-foreground mb-1">{title}</p>
      <div className="flex items-baseline gap-1">
        {isPositive ? (
          <ArrowUp className="w-4 h-4 text-green-600" />
        ) : (
          <ArrowDown className="w-4 h-4 text-red-600" />
        )}
        <span className={`text-lg font-bold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
          {formatCurrency(Math.abs(netFlow))}
        </span>
      </div>
      <p className="text-xs text-muted-foreground mt-1">
        Saldo: {formatCurrency(endingBalance)}
      </p>
    </button>
  );
}

export function CashFlowForecastWidget() {
  const [selectedPeriod, setSelectedPeriod] = useState<30 | 60 | 90>(30);
  const chartColors = useChartColors();

  // Real-time Widget Updates
  useWidgetSubscription('cashflow', {
    debounceMs: 500,
    autoInvalidate: true,
    queryKeysToInvalidate: [
      ['dashboard-widgets', 'cash-flow-forecast'],
      ['cashflow'],
    ],
  });

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery<CashFlowForecastData, Error>({
    queryKey: dashboardWidgetKeys.cashFlowForecast(),
    queryFn: () => getCashFlowForecast(),
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 mb-4">
            <Skeleton className="h-20 flex-1" />
            <Skeleton className="h-20 flex-1" />
            <Skeleton className="h-20 flex-1" />
          </div>
          <Skeleton className="h-[250px] w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wallet className="w-5 h-5" />
            Liquiditätsprognose
          </CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Prognose
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

  // Chart-Daten basierend auf ausgewählter Periode
  const chartData = data.dailyData.slice(0, selectedPeriod).map((point) => ({
    date: point.date,
    Einnahmen: point.income,
    Ausgaben: point.expenses,
    Saldo: point.balance,
  }));

  const selectedForecast =
    selectedPeriod === 30
      ? data.forecast30
      : selectedPeriod === 60
      ? data.forecast60
      : data.forecast90;

  return (
    <ErrorBoundary
      fallback={<DashboardSectionError section="Liquiditätsprognose" />}
      errorTitle="Prognose Fehler"
      errorDescription="Die Liquiditätsprognose konnte nicht geladen werden."
    >
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Wallet className="w-5 h-5" />
                Liquiditätsprognose
              </CardTitle>
              <CardDescription>
                Aktueller Saldo: {formatCurrency(data.currentBalance)}
              </CardDescription>
            </div>
            <Button variant="ghost" size="icon" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* Risikowarnung */}
          {data.riskWarning && (
            <Alert variant="destructive" className="mb-4">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{data.riskWarning}</AlertDescription>
            </Alert>
          )}

          {/* Perioden-Auswahl */}
          <div className="flex gap-2 mb-4">
            <PeriodCard
              title="30 Tage"
              income={data.forecast30.totalIncome}
              expenses={data.forecast30.totalExpenses}
              netFlow={data.forecast30.netFlow}
              endingBalance={data.forecast30.endingBalance}
              isActive={selectedPeriod === 30}
              onClick={() => setSelectedPeriod(30)}
            />
            <PeriodCard
              title="60 Tage"
              income={data.forecast60.totalIncome}
              expenses={data.forecast60.totalExpenses}
              netFlow={data.forecast60.netFlow}
              endingBalance={data.forecast60.endingBalance}
              isActive={selectedPeriod === 60}
              onClick={() => setSelectedPeriod(60)}
            />
            <PeriodCard
              title="90 Tage"
              income={data.forecast90.totalIncome}
              expenses={data.forecast90.totalExpenses}
              netFlow={data.forecast90.netFlow}
              endingBalance={data.forecast90.endingBalance}
              isActive={selectedPeriod === 90}
              onClick={() => setSelectedPeriod(90)}
            />
          </div>

          {/* Chart */}
          <div
            className="h-[250px]"
            role="img"
            aria-label={`Liquiditätsprognose für ${selectedPeriod} Tage`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorIncome" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={chartColors.income} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={chartColors.income} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorExpenses" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={chartColors.expenses} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={chartColors.expenses} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorBalance" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={chartColors.balance} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={chartColors.balance} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="date"
                  tickFormatter={formatDateShort}
                  tick={{ fontSize: 11 }}
                  tickMargin={8}
                />
                <YAxis
                  tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                  tick={{ fontSize: 11 }}
                  tickMargin={8}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="Einnahmen"
                  stroke={chartColors.income}
                  fill="url(#colorIncome)"
                  strokeWidth={2}
                />
                <Area
                  type="monotone"
                  dataKey="Ausgaben"
                  stroke={chartColors.expenses}
                  fill="url(#colorExpenses)"
                  strokeWidth={2}
                />
                <Area
                  type="monotone"
                  dataKey="Saldo"
                  stroke={chartColors.balance}
                  fill="url(#colorBalance)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Skonto-Hinweis */}
          {data.skontoImpact.invoiceCount > 0 && (
            <div className="mt-4 p-3 rounded-lg bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800">
              <div className="flex items-center gap-2 text-sm text-green-700 dark:text-green-400">
                <TrendingDown className="w-4 h-4" />
                <span>
                  {data.skontoImpact.invoiceCount} Skonto-Chancen mit{' '}
                  <strong>{formatCurrency(data.skontoImpact.potentialSavings)}</strong> Ersparnis
                </span>
              </div>
            </div>
          )}

          {/* Screen Reader Tabelle */}
          <table className="sr-only" aria-label="Prognosedaten als Tabelle">
            <caption>Tagesweise Einnahmen, Ausgaben und Saldo</caption>
            <thead>
              <tr>
                <th scope="col">Datum</th>
                <th scope="col">Einnahmen</th>
                <th scope="col">Ausgaben</th>
                <th scope="col">Saldo</th>
              </tr>
            </thead>
            <tbody>
              {chartData.map((entry, index) => (
                <tr key={index}>
                  <td>{formatDateShort(entry.date)}</td>
                  <td>{formatCurrency(entry.Einnahmen)}</td>
                  <td>{formatCurrency(entry.Ausgaben)}</td>
                  <td>{formatCurrency(entry.Saldo)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </ErrorBoundary>
  );
}
