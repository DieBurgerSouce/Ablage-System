/**
 * Cash Book Summary
 *
 * Zeigt eine Zusammenfassung der Kassenbewegungen (KPIs).
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ArrowUpRight,
  ArrowDownRight,
  Wallet,
  Receipt,
  Scale,
  TrendingUp,
} from 'lucide-react';
import { useCashSummary } from '../hooks/use-cash-queries';
import { formatCurrency } from '../utils/format';
import { cn } from '@/lib/utils';

interface CashBookSummaryProps {
  registerId: string;
  startDate?: string;
  endDate?: string;
  className?: string;
}

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  badge?: {
    label: string;
    variant: 'default' | 'secondary' | 'destructive' | 'outline';
  };
  isLoading?: boolean;
  valueClassName?: string;
}

function KPICard({ title, value, subtitle, icon, badge, isLoading, valueClassName }: KPICardProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-4" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-8 w-32 mb-1" />
          <Skeleton className="h-3 w-20" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <div className="text-muted-foreground">{icon}</div>
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline gap-2">
          <div className={cn('text-2xl font-bold', valueClassName)}>{value}</div>
          {badge && (
            <Badge variant={badge.variant} className="text-xs">
              {badge.label}
            </Badge>
          )}
        </div>
        {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
      </CardContent>
    </Card>
  );
}

export function CashBookSummary({ registerId, startDate, endDate, className }: CashBookSummaryProps) {
  const { data: summary, isLoading } = useCashSummary(registerId, startDate, endDate);

  const totalIncome = summary?.total_income ?? 0;
  const totalExpense = summary?.total_expense ?? 0;
  const netChange = totalIncome - totalExpense;
  const entryCount = summary?.entry_count ?? 0;
  const currentBalance = summary?.current_balance ?? 0;

  // Balance-Status ermitteln
  const balanceStatus = currentBalance < 0
    ? { label: 'Negativ', variant: 'destructive' as const }
    : currentBalance < 100
    ? { label: 'Niedrig', variant: 'secondary' as const }
    : undefined;

  return (
    <div className={cn('grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5', className)}>
      {/* Aktueller Kassenstand */}
      <KPICard
        title="Kassenstand"
        value={formatCurrency(currentBalance)}
        subtitle={summary?.register_name}
        icon={<Wallet className="h-4 w-4" aria-hidden="true" />}
        badge={balanceStatus}
        isLoading={isLoading}
        valueClassName={currentBalance < 0 ? 'text-destructive' : undefined}
      />

      {/* Einnahmen */}
      <KPICard
        title="Einnahmen"
        value={formatCurrency(totalIncome)}
        subtitle={startDate && endDate ? `${startDate} - ${endDate}` : 'Gesamt'}
        icon={<ArrowUpRight className="h-4 w-4 text-green-600" aria-hidden="true" />}
        isLoading={isLoading}
        valueClassName="text-green-600"
      />

      {/* Ausgaben */}
      <KPICard
        title="Ausgaben"
        value={formatCurrency(totalExpense)}
        subtitle={startDate && endDate ? `${startDate} - ${endDate}` : 'Gesamt'}
        icon={<ArrowDownRight className="h-4 w-4 text-red-600" aria-hidden="true" />}
        isLoading={isLoading}
        valueClassName="text-red-600"
      />

      {/* Netto-Änderung */}
      <KPICard
        title="Netto"
        value={formatCurrency(netChange)}
        subtitle={netChange >= 0 ? 'Überschuss' : 'Defizit'}
        icon={<TrendingUp className="h-4 w-4" aria-hidden="true" />}
        badge={
          netChange > 0
            ? { label: '+', variant: 'default' }
            : netChange < 0
            ? { label: '-', variant: 'destructive' }
            : undefined
        }
        isLoading={isLoading}
        valueClassName={netChange >= 0 ? 'text-green-600' : 'text-red-600'}
      />

      {/* Anzahl Buchungen */}
      <KPICard
        title="Buchungen"
        value={entryCount}
        subtitle="Einträge im Zeitraum"
        icon={<Receipt className="h-4 w-4" aria-hidden="true" />}
        isLoading={isLoading}
      />
    </div>
  );
}

export default CashBookSummary;
