/**
 * InvoiceStatsCards - KPI Dashboard Cards
 *
 * Zeigt aggregierte Statistiken:
 * - Offene Forderungen (EUR)
 * - Überfällige Forderungen (EUR)
 * - Durchschnittliches Zahlungsziel (Tage)
 * - Aktive Mahnungen (Anzahl)
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Euro, Clock, AlertTriangle, FileWarning } from 'lucide-react';
import type { InvoiceStatisticsResponse } from '../types/invoice-types';
import { UI_LABELS } from '../types/invoice-types';
import { computeKPIs } from '../api/invoice-api';

interface InvoiceStatsCardsProps {
  statistics?: InvoiceStatisticsResponse;
  isLoading: boolean;
}

/**
 * Formatiert einen Betrag als Euro-Währung
 */
function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function InvoiceStatsCards({
  statistics,
  isLoading,
}: InvoiceStatsCardsProps) {
  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-4" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-32 mb-1" />
              <Skeleton className="h-3 w-20" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!statistics) {
    return null;
  }

  const kpis = computeKPIs(statistics);

  const cards = [
    {
      title: UI_LABELS.statOpenAmount,
      value: formatCurrency(kpis.openAmount),
      subtitle: `${statistics.totalInvoices} Rechnungen gesamt`,
      icon: Euro,
      iconClassName: 'text-blue-500',
    },
    {
      title: UI_LABELS.statOverdueAmount,
      value: formatCurrency(kpis.overdueAmount),
      subtitle: `${statistics.overdueInvoices.count} überfällig`,
      icon: Clock,
      iconClassName: 'text-red-500',
      valueClassName: kpis.overdueAmount > 0 ? 'text-red-600' : undefined,
    },
    {
      title: UI_LABELS.statAvgPaymentDays,
      value: '-',  // Would need backend calculation
      subtitle: 'Durchschnitt',
      icon: FileWarning,
      iconClassName: 'text-yellow-500',
    },
    {
      title: UI_LABELS.statActiveDunnings,
      value: kpis.activeDunnings.toString(),
      subtitle: 'In Mahnung',
      icon: AlertTriangle,
      iconClassName: kpis.activeDunnings > 0 ? 'text-orange-500' : 'text-gray-400',
      valueClassName: kpis.activeDunnings > 0 ? 'text-orange-600' : undefined,
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title}>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {card.title}
            </CardTitle>
            <card.icon className={`h-4 w-4 ${card.iconClassName}`} />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${card.valueClassName ?? ''}`}>
              {card.value}
            </div>
            <p className="text-xs text-muted-foreground">{card.subtitle}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
