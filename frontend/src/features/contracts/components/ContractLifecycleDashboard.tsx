/**
 * ContractLifecycleDashboard - Vertrags-Lifecycle Uebersicht
 *
 * Features:
 * - 4 KPI-Karten (Aktive Vertraege, Bald ablaufend, Entscheidung noetig, Jahreskosten)
 * - Kostenaufschluesselung nach Kategorie/Lieferant
 * - Monatlicher Kostentrend (Balkendiagramm)
 * - Verlaengerungstracker
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { CheckCircle, Clock, AlertTriangle, Euro } from 'lucide-react';
import { useContractLifecycle } from '../api/contract-lifecycle-api';
import { ContractCostBreakdown } from './ContractCostBreakdown';
import { ContractRenewalTracker } from './ContractRenewalTracker';

interface ContractLifecycleDashboardProps {
  onViewContract?: (contractId: string) => void;
  onRenewContract?: (contractId: string) => void;
  onTerminateContract?: (contractId: string) => void;
}

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

const formatCurrencyShort = (value: number): string => {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toLocaleString('de-DE', { maximumFractionDigits: 1 })} Mio. EUR`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toLocaleString('de-DE', { maximumFractionDigits: 0 })} Tsd. EUR`;
  }
  return formatCurrency(value);
};

export function ContractLifecycleDashboard({
  onViewContract,
  onRenewContract,
  onTerminateContract,
}: ContractLifecycleDashboardProps) {
  const { data: lifecycle, isLoading } = useContractLifecycle();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const kpis = [
    {
      title: 'Aktive Vertraege',
      value: lifecycle?.active_contracts ?? 0,
      icon: CheckCircle,
      color: 'text-green-600',
      bgColor: 'bg-green-100',
      formatted: (lifecycle?.active_contracts ?? 0).toLocaleString('de-DE'),
    },
    {
      title: 'Bald ablaufend',
      value: lifecycle?.expiring_soon ?? 0,
      icon: Clock,
      color: 'text-orange-600',
      bgColor: 'bg-orange-100',
      description: 'Naechste 90 Tage',
      formatted: (lifecycle?.expiring_soon ?? 0).toLocaleString('de-DE'),
    },
    {
      title: 'Entscheidung noetig',
      value: lifecycle?.pending_renewal_decision ?? 0,
      icon: AlertTriangle,
      color: 'text-red-600',
      bgColor: 'bg-red-100',
      description: 'Verlaengerung ausstehend',
      formatted: (lifecycle?.pending_renewal_decision ?? 0).toLocaleString('de-DE'),
    },
    {
      title: 'Jahreskosten gesamt',
      value: lifecycle?.cost_summary?.total_annual_cost ?? 0,
      icon: Euro,
      color: 'text-purple-600',
      bgColor: 'bg-purple-100',
      description: `Monatlich: ${formatCurrency(lifecycle?.cost_summary?.total_monthly_cost ?? 0)}`,
      formatted: formatCurrencyShort(lifecycle?.cost_summary?.total_annual_cost ?? 0),
    },
  ];

  const trendData = lifecycle?.cost_summary?.trend_last_12_months ?? [];
  const maxTrendCost = Math.max(...trendData.map((t) => t.total_cost), 1);

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {kpis.map((kpi) => (
          <Card key={kpi.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {kpi.title}
              </CardTitle>
              <div className={`p-2 rounded-full ${kpi.bgColor}`}>
                <kpi.icon className={`h-4 w-4 ${kpi.color}`} />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{kpi.formatted}</div>
              {kpi.description && (
                <p className="text-xs text-muted-foreground mt-1">{kpi.description}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Monthly Cost Trend */}
      {trendData.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Monatlicher Kostentrend</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end gap-2 h-48">
              {trendData.map((item) => {
                const barHeight = (item.total_cost / maxTrendCost) * 100;
                const monthLabel = item.month.length >= 7
                  ? item.month.substring(5, 7) + '/' + item.month.substring(2, 4)
                  : item.month;

                return (
                  <div
                    key={item.month}
                    className="flex-1 flex flex-col items-center gap-1 group"
                    title={`${item.month}: ${formatCurrency(item.total_cost)}`}
                  >
                    <div className="relative w-full flex items-end justify-center h-40">
                      <div
                        className="w-full max-w-10 bg-primary/80 rounded-t transition-all hover:bg-primary"
                        style={{ height: `${Math.max(barHeight, 2)}%` }}
                      />
                      <div className="absolute -top-6 left-1/2 -translate-x-1/2 hidden group-hover:block bg-popover text-popover-foreground shadow-md rounded px-2 py-1 text-xs whitespace-nowrap z-10">
                        {formatCurrency(item.total_cost)}
                      </div>
                    </div>
                    <span className="text-xs text-muted-foreground">{monthLabel}</span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Cost Breakdown */}
      <ContractCostBreakdown
        costSummary={lifecycle?.cost_summary}
        isLoading={false}
      />

      {/* Renewal Tracker */}
      <ContractRenewalTracker
        renewals={lifecycle?.upcoming_renewals}
        isLoading={false}
        onViewContract={onViewContract}
        onRenewContract={onRenewContract}
        onTerminateContract={onTerminateContract}
      />
    </div>
  );
}
