/**
 * CashflowForecastChart Component
 *
 * 30/60/90 day forecast visualization with CSS-based bars
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { TrendingUp, TrendingDown, Calendar } from 'lucide-react';
import { useCashflowForecast } from '../hooks/use-german-finance-queries';
import type { CashflowForecast } from '../types/german-finance-types';
import { UI_LABELS } from '../types/german-finance-types';

const formatEuro = (amount: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

const formatDate = (date: Date): string => {
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: 'short',
  });
};

interface ForecastBarProps {
  label: string;
  income: number;
  expenses: number;
  net: number;
  cumulative: number;
  confidence: number;
  maxValue: number;
}

function ForecastBar({
  label,
  income,
  expenses,
  net,
  cumulative,
  confidence,
  maxValue,
}: ForecastBarProps) {
  const incomePercent = Math.min((Math.abs(income) / maxValue) * 100, 100);
  const expensesPercent = Math.min((Math.abs(expenses) / maxValue) * 100, 100);
  const isPositive = net >= 0;

  return (
    <div className="space-y-2 border-b pb-4 last:border-b-0">
      {/* Date Label */}
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-xs text-muted-foreground">
          Konfidenz: {confidence}%
        </span>
      </div>

      {/* Income Bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="text-green-600">Einnahmen</span>
          <span className="font-medium text-green-600">{formatEuro(income)}</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-green-500"
            style={{ width: `${incomePercent}%` }}
          />
        </div>
      </div>

      {/* Expenses Bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="text-red-600">Ausgaben</span>
          <span className="font-medium text-red-600">{formatEuro(expenses)}</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-red-500"
            style={{ width: `${expensesPercent}%` }}
          />
        </div>
      </div>

      {/* Net Cashflow */}
      <div className="flex items-center justify-between rounded-md bg-muted/50 p-2">
        <div className="flex items-center gap-2">
          {isPositive ? (
            <TrendingUp className="h-4 w-4 text-green-600" />
          ) : (
            <TrendingDown className="h-4 w-4 text-red-600" />
          )}
          <span className="text-sm font-medium">Netto</span>
        </div>
        <span className={`font-bold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
          {formatEuro(net)}
        </span>
      </div>

      {/* Cumulative */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">Kumuliert</span>
        <span
          className={`font-semibold ${
            cumulative >= 0 ? 'text-green-600' : 'text-red-600'
          }`}
        >
          {formatEuro(cumulative)}
        </span>
      </div>
    </div>
  );
}

interface CashflowForecastChartProps {
  defaultDays?: 30 | 60 | 90;
}

export function CashflowForecastChart({ defaultDays = 30 }: CashflowForecastChartProps) {
  const { data: forecast30, isLoading: loading30 } = useCashflowForecast(30);
  const { data: forecast60, isLoading: loading60 } = useCashflowForecast(60);
  const { data: forecast90, isLoading: loading90 } = useCashflowForecast(90);

  const renderForecast = (
    forecast: CashflowForecast[] | undefined,
    isLoading: boolean
  ) => {
    if (isLoading) {
      return (
        <div className="space-y-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      );
    }

    if (!forecast || forecast.length === 0) {
      return (
        <div className="flex h-64 items-center justify-center text-muted-foreground">
          {UI_LABELS.common.noData}
        </div>
      );
    }

    // Calculate max value for scaling bars
    const maxValue = Math.max(
      ...forecast.map((f) => Math.max(Math.abs(f.expectedIncome), Math.abs(f.expectedExpenses)))
    );

    return (
      <div className="space-y-4">
        {forecast.map((item, index) => (
          <ForecastBar
            key={index}
            label={formatDate(item.date)}
            income={item.expectedIncome}
            expenses={item.expectedExpenses}
            net={item.netCashflow}
            cumulative={item.cumulative}
            confidence={item.confidence}
            maxValue={maxValue}
          />
        ))}
      </div>
    );
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Calendar className="h-5 w-5" />
          <div>
            <CardTitle>{UI_LABELS.cashflow.forecast}</CardTitle>
            <CardDescription>
              Erwartete Einnahmen und Ausgaben für die nächsten 30, 60 oder 90 Tage
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue={defaultDays.toString()}>
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="30">30 Tage</TabsTrigger>
            <TabsTrigger value="60">60 Tage</TabsTrigger>
            <TabsTrigger value="90">90 Tage</TabsTrigger>
          </TabsList>
          <TabsContent value="30" className="mt-6">
            {renderForecast(forecast30, loading30)}
          </TabsContent>
          <TabsContent value="60" className="mt-6">
            {renderForecast(forecast60, loading60)}
          </TabsContent>
          <TabsContent value="90" className="mt-6">
            {renderForecast(forecast90, loading90)}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
