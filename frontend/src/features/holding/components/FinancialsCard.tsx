/**
 * Financials Card Component
 *
 * Zeigt konsolidierte Finanzkennzahlen (Forderungen/Verbindlichkeiten).
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { ArrowUpRight, ArrowDownRight, AlertTriangle } from 'lucide-react';
import type { Financials } from '../api/holding-api';

interface FinancialsCardProps {
  financials: Financials;
}

export function FinancialsCard({ financials }: FinancialsCardProps) {
  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: financials.currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);

  const overdueReceivablesPercent =
    financials.total_receivables > 0
      ? (financials.overdue_receivables / financials.total_receivables) * 100
      : 0;

  const overduePayablesPercent =
    financials.total_payables > 0
      ? (financials.overdue_payables / financials.total_payables) * 100
      : 0;

  const isPositive = financials.net_position >= 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span>Finanzkennzahlen</span>
        </CardTitle>
        <CardDescription>Konsolidierte Forderungen und Verbindlichkeiten</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Net Position */}
        <div
          className={`p-4 rounded-lg ${
            isPositive ? 'bg-green-50 dark:bg-green-950' : 'bg-red-50 dark:bg-red-950'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Netto-Position</span>
            {isPositive ? (
              <ArrowUpRight className="h-4 w-4 text-green-600" />
            ) : (
              <ArrowDownRight className="h-4 w-4 text-red-600" />
            )}
          </div>
          <div
            className={`text-2xl font-bold mt-1 ${
              isPositive ? 'text-green-600' : 'text-red-600'
            }`}
          >
            {formatCurrency(financials.net_position)}
          </div>
        </div>

        {/* Receivables */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Forderungen (offen)</span>
            <span className="font-medium">{formatCurrency(financials.total_receivables)}</span>
          </div>
          <Progress value={100} className="h-2 bg-blue-100" />
          {financials.overdue_receivables > 0 && (
            <div className="flex items-center gap-1 text-xs text-amber-600">
              <AlertTriangle className="h-3 w-3" />
              <span>
                {formatCurrency(financials.overdue_receivables)} überfällig (
                {overdueReceivablesPercent.toFixed(0)}%)
              </span>
            </div>
          )}
        </div>

        {/* Payables */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Verbindlichkeiten (offen)</span>
            <span className="font-medium">{formatCurrency(financials.total_payables)}</span>
          </div>
          <Progress value={100} className="h-2 bg-orange-100" />
          {financials.overdue_payables > 0 && (
            <div className="flex items-center gap-1 text-xs text-red-600">
              <AlertTriangle className="h-3 w-3" />
              <span>
                {formatCurrency(financials.overdue_payables)} überfällig (
                {overduePayablesPercent.toFixed(0)}%)
              </span>
            </div>
          )}
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-2 gap-4 pt-2 border-t">
          <div className="text-center">
            <div className="text-xs text-muted-foreground">Überfällig (Ein)</div>
            <div className="text-lg font-medium text-amber-600">
              {formatCurrency(financials.overdue_receivables)}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-muted-foreground">Überfällig (Aus)</div>
            <div className="text-lg font-medium text-red-600">
              {formatCurrency(financials.overdue_payables)}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
