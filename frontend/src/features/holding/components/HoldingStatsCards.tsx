/**
 * Holding Stats Cards
 *
 * Übersichtskarten mit Key-Metriken der Holding.
 */

import { Card, CardContent } from '@/components/ui/card';
import {
  Building2,
  FileText,
  Receipt,
  Wallet,
  TrendingUp,
  TrendingDown,
  Clock,
  AlertCircle,
} from 'lucide-react';
import type { ConsolidatedOverview } from '../api/holding-api';

interface HoldingStatsCardsProps {
  overview: ConsolidatedOverview;
}

export function HoldingStatsCards({ overview }: HoldingStatsCardsProps) {
  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);

  const stats = [
    {
      label: 'Firmen',
      value: overview.company_count.toString(),
      icon: Building2,
      color: 'text-blue-600',
      bgColor: 'bg-blue-50 dark:bg-blue-950',
    },
    {
      label: 'Dokumente (gesamt)',
      value: overview.documents.total.toLocaleString('de-DE'),
      subValue: `+${overview.documents.this_month} diesen Monat`,
      icon: FileText,
      color: 'text-purple-600',
      bgColor: 'bg-purple-50 dark:bg-purple-950',
    },
    {
      label: 'Offene Rechnungen',
      value: (overview.invoices.open_outgoing + overview.invoices.open_incoming).toString(),
      subValue: `${overview.invoices.open_outgoing} aus, ${overview.invoices.open_incoming} ein`,
      icon: Receipt,
      color: 'text-amber-600',
      bgColor: 'bg-amber-50 dark:bg-amber-950',
    },
    {
      label: 'Kontostand (gesamt)',
      value: formatCurrency(overview.banking.total_balance),
      subValue: `${overview.banking.account_count} Konten`,
      icon: Wallet,
      color: 'text-green-600',
      bgColor: 'bg-green-50 dark:bg-green-950',
    },
    {
      label: 'Forderungen',
      value: formatCurrency(overview.financials.total_receivables),
      subValue: overview.financials.overdue_receivables > 0
        ? `${formatCurrency(overview.financials.overdue_receivables)} überfällig`
        : undefined,
      icon: TrendingUp,
      color: 'text-blue-600',
      bgColor: 'bg-blue-50 dark:bg-blue-950',
      alert: overview.financials.overdue_receivables > 0,
    },
    {
      label: 'Verbindlichkeiten',
      value: formatCurrency(overview.financials.total_payables),
      subValue: overview.financials.overdue_payables > 0
        ? `${formatCurrency(overview.financials.overdue_payables)} überfällig`
        : undefined,
      icon: TrendingDown,
      color: 'text-orange-600',
      bgColor: 'bg-orange-50 dark:bg-orange-950',
      alert: overview.financials.overdue_payables > 0,
    },
    {
      label: 'Zahlungsdauer (Ø)',
      value: overview.invoices.avg_payment_days !== null
        ? `${overview.invoices.avg_payment_days} Tage`
        : '-',
      icon: Clock,
      color: 'text-slate-600',
      bgColor: 'bg-slate-50 dark:bg-slate-950',
    },
    {
      label: 'Transaktionen (30d)',
      value: overview.banking.transactions_last_30d.toLocaleString('de-DE'),
      icon: Receipt,
      color: 'text-cyan-600',
      bgColor: 'bg-cyan-50 dark:bg-cyan-950',
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {stats.map((stat, index) => {
        const Icon = stat.icon;
        return (
          <Card key={index} className={stat.bgColor}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">{stat.label}</p>
                  <p className={`text-xl font-bold ${stat.color}`}>{stat.value}</p>
                  {stat.subValue && (
                    <p className={`text-xs ${stat.alert ? 'text-red-600 font-medium' : 'text-muted-foreground'}`}>
                      {stat.alert && <AlertCircle className="inline h-3 w-3 mr-1" />}
                      {stat.subValue}
                    </p>
                  )}
                </div>
                <Icon className={`h-5 w-5 ${stat.color} opacity-70`} />
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
