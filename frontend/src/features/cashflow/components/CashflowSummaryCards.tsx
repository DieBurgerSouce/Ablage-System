/**
 * Cashflow Summary Cards
 *
 * Kompakte Übersicht der wichtigsten Cashflow-Kennzahlen.
 */

import { Card, CardContent } from '@/components/ui/card';
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Clock,
  Euro,
} from 'lucide-react';
import type { CashflowSummary } from '../api/cashflow-api';

interface CashflowSummaryCardsProps {
  summary: CashflowSummary;
}

export function CashflowSummaryCards({ summary }: CashflowSummaryCardsProps) {
  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: summary.currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);

  const statusConfig = {
    healthy: { label: 'Gesund', color: 'text-green-600', bg: 'bg-green-50 dark:bg-green-950' },
    warning: { label: 'Warnung', color: 'text-amber-600', bg: 'bg-amber-50 dark:bg-amber-950' },
    critical: { label: 'Kritisch', color: 'text-red-600', bg: 'bg-red-50 dark:bg-red-950' },
  };

  const status = statusConfig[summary.status] || statusConfig.healthy;

  const cards = [
    {
      label: 'Aktueller Stand',
      value: formatCurrency(summary.current_balance),
      icon: Wallet,
      color: summary.current_balance >= 0 ? 'text-green-600' : 'text-red-600',
      bg: summary.current_balance >= 0 ? 'bg-green-50 dark:bg-green-950' : 'bg-red-50 dark:bg-red-950',
    },
    {
      label: 'Min. 7 Tage',
      value: formatCurrency(summary.min_balance_7d),
      icon: TrendingDown,
      color: summary.min_balance_7d >= 0 ? 'text-slate-600' : 'text-red-600',
      bg: summary.min_balance_7d >= 0 ? 'bg-slate-50 dark:bg-slate-950' : 'bg-red-50 dark:bg-red-950',
    },
    {
      label: 'Min. 30 Tage',
      value: formatCurrency(summary.min_balance_30d),
      icon: TrendingDown,
      color: summary.min_balance_30d >= 0 ? 'text-slate-600' : 'text-red-600',
      bg: summary.min_balance_30d >= 0 ? 'bg-slate-50 dark:bg-slate-950' : 'bg-red-50 dark:bg-red-950',
    },
    {
      label: 'Erw. Eingänge (7d)',
      value: formatCurrency(summary.expected_inflows_7d),
      icon: TrendingUp,
      color: 'text-green-600',
      bg: 'bg-green-50 dark:bg-green-950',
    },
    {
      label: 'Erw. Ausgänge (7d)',
      value: formatCurrency(summary.expected_outflows_7d),
      icon: TrendingDown,
      color: 'text-orange-600',
      bg: 'bg-orange-50 dark:bg-orange-950',
    },
    {
      label: 'Dringende Zahlungen',
      value: summary.urgent_payments.toString(),
      icon: Clock,
      color: summary.urgent_payments > 0 ? 'text-red-600' : 'text-slate-600',
      bg: summary.urgent_payments > 0 ? 'bg-red-50 dark:bg-red-950' : 'bg-slate-50 dark:bg-slate-950',
    },
    {
      label: 'Skonto-Potential',
      value: formatCurrency(summary.potential_skonto_savings),
      icon: Euro,
      color: summary.potential_skonto_savings > 0 ? 'text-green-600' : 'text-slate-600',
      bg: summary.potential_skonto_savings > 0 ? 'bg-green-50 dark:bg-green-950' : 'bg-slate-50 dark:bg-slate-950',
    },
    {
      label: 'Status',
      value: status.label,
      icon: AlertTriangle,
      color: status.color,
      bg: status.bg,
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map((card, index) => {
        const Icon = card.icon;
        return (
          <Card key={index} className={card.bg}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">{card.label}</p>
                  <p className={`text-xl font-bold ${card.color}`}>{card.value}</p>
                </div>
                <Icon className={`h-5 w-5 ${card.color} opacity-70`} />
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
