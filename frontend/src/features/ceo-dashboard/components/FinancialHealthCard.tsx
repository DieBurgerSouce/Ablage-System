/**
 * Financial Health Card Component
 *
 * Displays financial health score and key metrics.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import type { FinancialHealth } from '../types/digital-twin-types';
import { getHealthScoreColor } from '../types/digital-twin-types';
import { TrendingUp, TrendingDown, Wallet } from 'lucide-react';

interface FinancialHealthCardProps {
  data: FinancialHealth;
}

export function FinancialHealthCard({ data }: FinancialHealthCardProps) {
  const colors = getHealthScoreColor(data.healthScore);

  // Format currency
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Wallet className="w-5 h-5" />
          Finanzielle Gesundheit
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Health Score Gauge */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Gesundheitsscore</span>
            <span className={`text-2xl font-bold ${colors.text}`}>
              {Math.round(data.healthScore)}
            </span>
          </div>
          <Progress
            value={data.healthScore}
            className="h-3"
            indicatorClassName={colors.text}
          />
        </div>

        {/* Cashflow */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              Aktueller Cashflow
            </span>
            <div className="flex items-center gap-1">
              {data.cashflowCurrent >= 0 ? (
                <TrendingUp className="w-4 h-4 text-green-500" />
              ) : (
                <TrendingDown className="w-4 h-4 text-red-500" />
              )}
              <span
                className={`font-semibold ${
                  data.cashflowCurrent >= 0 ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'
                }`}
              >
                {formatCurrency(data.cashflowCurrent)}
              </span>
            </div>
          </div>
        </div>

        {/* Receivables */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground">Forderungen</div>
            <div className="font-semibold">
              {formatCurrency(data.receivablesTotal)}
            </div>
            {data.overdueReceivables > 0 && (
              <div className="text-xs text-red-600 dark:text-red-400">
                {formatCurrency(data.overdueReceivables)} überfällig
              </div>
            )}
          </div>

          {/* Payables */}
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground">Verbindlichkeiten</div>
            <div className="font-semibold">
              {formatCurrency(data.payablesTotal)}
            </div>
            {data.overduePayables > 0 && (
              <div className="text-xs text-orange-600 dark:text-orange-400">
                {formatCurrency(data.overduePayables)} überfällig
              </div>
            )}
          </div>
        </div>

        {/* Liquidity Ratio */}
        <div className="pt-4 border-t border-border">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Liquiditätsquote</span>
            <span
              className={`font-bold ${
                data.liquidityRatio >= 1.5
                  ? 'text-green-700 dark:text-green-400'
                  : data.liquidityRatio >= 1.0
                    ? 'text-yellow-700 dark:text-yellow-400'
                    : 'text-red-700 dark:text-red-400'
              }`}
            >
              {data.liquidityRatio.toFixed(2)}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
