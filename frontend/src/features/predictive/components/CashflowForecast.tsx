/**
 * CashflowForecast - 30/60/90 Tage Cashflow-Prognose
 *
 * Zeigt eine visuelle Balkenansicht der prognostizierten Kontosalden
 * mit Warnungen fuer kritische Liquiditaetsengpaesse.
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Loader2,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useCashflowForecast } from '../hooks/use-predictions';
import type { ForecastPeriod } from '../types/predictive-types';

const formatCurrency = (amount: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);

export function CashflowForecast() {
  const [period, setPeriod] = useState<ForecastPeriod>('30');
  const { data, isLoading, isError } = useCashflowForecast(period);

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Lade Cashflow-Prognose...
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          Cashflow-Daten nicht verfuegbar
        </CardContent>
      </Card>
    );
  }

  const days = data.forecast_days || [];
  const maxBalance = Math.max(...days.map((d) => Math.abs(d.balance)), 1);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <TrendingUp className="h-5 w-5" />
            Cashflow-Prognose
          </CardTitle>
          <Select
            value={period}
            onValueChange={(v) => setPeriod(v as ForecastPeriod)}
          >
            <SelectTrigger className="w-28 h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="30">30 Tage</SelectItem>
              <SelectItem value="60">60 Tage</SelectItem>
              <SelectItem value="90">90 Tage</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>

      <CardContent>
        {/* Warnungen */}
        {data.warnings && data.warnings.length > 0 && (
          <div className="mb-4 space-y-1">
            {data.warnings.map((warning, i) => (
              <div
                key={i}
                className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 dark:bg-amber-950/30 px-3 py-1.5 rounded"
              >
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                {warning.message}
              </div>
            ))}
          </div>
        )}

        {/* Balkendiagramm */}
        <div className="space-y-1">
          {days.slice(0, 30).map((day) => {
            const barWidth = (Math.abs(day.balance) / maxBalance) * 100;
            const isPositive = day.balance >= 0;

            return (
              <div
                key={day.date}
                className="flex items-center gap-2 text-xs h-6 group"
              >
                <span className="w-16 text-muted-foreground shrink-0">
                  {new Date(day.date).toLocaleDateString('de-DE', {
                    day: '2-digit',
                    month: '2-digit',
                  })}
                </span>
                <div className="flex-1 h-4 bg-muted/30 rounded-sm relative overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-sm transition-all',
                      isPositive ? 'bg-green-500/70' : 'bg-red-500/70',
                      day.is_critical && 'bg-red-600',
                      day.is_warning && !day.is_critical && 'bg-amber-500/70',
                    )}
                    style={{ width: `${Math.min(barWidth, 100)}%` }}
                  />
                </div>
                <span
                  className={cn(
                    'w-24 text-right font-mono shrink-0',
                    isPositive ? 'text-green-600' : 'text-red-600',
                  )}
                >
                  {formatCurrency(day.balance)}
                </span>
                {day.is_critical && (
                  <AlertTriangle className="h-3 w-3 text-red-500 shrink-0" />
                )}
              </div>
            );
          })}
        </div>

        {/* Zusammenfassung */}
        <div className="mt-4 pt-3 border-t flex justify-between text-xs">
          <div className="flex items-center gap-1 text-green-600">
            <TrendingUp className="h-3.5 w-3.5" />
            Einnahmen:{' '}
            {formatCurrency(days.reduce((sum, d) => sum + d.inflows, 0))}
          </div>
          <div className="flex items-center gap-1 text-red-600">
            <TrendingDown className="h-3.5 w-3.5" />
            Ausgaben:{' '}
            {formatCurrency(days.reduce((sum, d) => sum + d.outflows, 0))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
