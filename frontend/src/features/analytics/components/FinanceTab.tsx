// Finance Tab Component
// Displays financial metrics: open items, overdue, skonto, cashflow trend, aging

import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { StatCard } from './StatCard';
import { MiniChart } from './MiniChart';
import { useFinanceData } from '../hooks/use-analytics-queries';
import {
  type AnalyticsPeriod,
  type StatCardData,
  UI_LABELS,
  formatCurrency,
  formatNumber,
} from '../types/analytics-types';

interface FinanceTabProps {
  period: AnalyticsPeriod;
}

export function FinanceTab({ period }: FinanceTabProps) {
  const { data, isLoading, isError } = useFinanceData(period);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 grid-cols-2 md:grid-cols-3">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        {UI_LABELS.ERROR}
      </div>
    );
  }

  const stats: StatCardData[] = [
    {
      label: UI_LABELS.OPEN_ITEMS,
      value: formatNumber(data.openItemsCount),
      unit: formatCurrency(data.openItemsAmount),
    },
    {
      label: UI_LABELS.OVERDUE_ITEMS,
      value: formatNumber(data.overdueCount),
      unit: formatCurrency(data.overdueAmount),
      color: data.overdueCount > 0 ? 'red' : 'green',
    },
    {
      label: UI_LABELS.SKONTO_REALIZED,
      value: formatCurrency(data.skontoRealized),
      color: 'green',
    },
    {
      label: UI_LABELS.SKONTO_MISSED,
      value: formatCurrency(data.skontoMissed),
      color: data.skontoMissed > 0 ? 'red' : 'green',
    },
  ];

  // Transform cashflow trend for chart
  const cashflowChartData = data.cashflowTrend.map((point) => ({
    name: new Date(point.date).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }),
    amount: point.amount,
  }));

  // Transform aging buckets for chart
  const agingChartData = data.agingBuckets.map((bucket) => ({
    name: bucket.bucket,
    count: bucket.count,
    amount: bucket.amount,
  }));

  // Transform dunning stages for chart
  const dunningChartData = data.dunningStages.map((stage) => ({
    name: `Stufe ${stage.stage}`,
    count: stage.count,
  }));

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
        {stats.map((stat) => (
          <StatCard key={stat.label} stat={stat} />
        ))}
      </div>

      {/* Charts */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Cashflow Trend */}
        {cashflowChartData.length > 0 && (
          <Card className="lg:col-span-2">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                {UI_LABELS.CASHFLOW_TREND}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <MiniChart
                data={cashflowChartData}
                type="area"
                dataKey="amount"
                height={180}
                color="#3b82f6"
              />
            </CardContent>
          </Card>
        )}

        {/* Aging Buckets */}
        {agingChartData.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                {UI_LABELS.AGING_BUCKETS}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <MiniChart
                data={agingChartData}
                type="bar"
                dataKey="count"
                height={180}
                color="#f59e0b"
              />
            </CardContent>
          </Card>
        )}

        {/* Dunning Stages */}
        {dunningChartData.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                {UI_LABELS.DUNNING_STAGES}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <MiniChart
                data={dunningChartData}
                type="bar"
                dataKey="count"
                height={180}
                color="#ef4444"
              />
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
