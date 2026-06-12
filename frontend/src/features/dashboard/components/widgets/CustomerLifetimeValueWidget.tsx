/**
 * Customer Lifetime Value Widget
 *
 * Dashboard-Widget für Kundenwert-Analyse.
 *
 * Features:
 * - Kumulativer Umsatz pro Kunde
 * - Trend-Analyse (wachsend/rückläufig)
 * - Churn-Risiko-Indikator
 * - Top-Kunden-Ranking
 *
 * Phase 7: Dashboard Widgets
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  RefreshCw,
  Users,
  Crown,
  AlertCircle,
} from 'lucide-react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';
import { getCustomerLTV, dashboardWidgetKeys, formatChurnRiskLabel, type CustomerLTVData, type CustomerMetrics, type AtRiskCustomer } from '../../api/dashboard-widgets';

/**
 * Formatiere Währung
 */
function formatCurrency(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * Formatiere kompakte Zahl
 */
function formatCompact(value: number): string {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return value.toFixed(0);
}

/**
 * Hole Churn-Risiko Badge-Variante
 */
function getChurnBadgeVariant(
  risk: 'low' | 'medium' | 'high' | 'critical'
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (risk) {
    case 'low':
      return 'secondary';
    case 'medium':
      return 'outline';
    case 'high':
      return 'default';
    case 'critical':
      return 'destructive';
    default:
      return 'outline';
  }
}

/**
 * Hole Trend-Farbe
 */
function getTrendColor(trend: 'growing' | 'stable' | 'declining'): string {
  switch (trend) {
    case 'growing':
      return 'text-green-600';
    case 'declining':
      return 'text-red-600';
    default:
      return 'text-muted-foreground';
  }
}

interface TrendBadgeProps {
  trend: 'growing' | 'stable' | 'declining';
  percentage: number;
}

function TrendBadge({ trend, percentage }: TrendBadgeProps) {
  const Icon = trend === 'growing' ? TrendingUp : trend === 'declining' ? TrendingDown : Minus;
  const color = getTrendColor(trend);

  return (
    <span className={`flex items-center gap-1 text-sm ${color}`}>
      <Icon className="w-3 h-3" />
      {percentage > 0 && '+'}
      {percentage.toFixed(1)}%
    </span>
  );
}

interface KPICardProps {
  label: string;
  value: string;
  subValue?: string;
  icon: React.ReactNode;
  trend?: 'growing' | 'stable' | 'declining';
  trendValue?: number;
}

function KPICard({ label, value, subValue, icon, trend, trendValue }: KPICardProps) {
  return (
    <div className="p-4 rounded-lg bg-muted/50">
      <div className="flex items-center gap-2 mb-2">
        <div className="p-1.5 rounded bg-background">{icon}</div>
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <p className="text-2xl font-bold">{value}</p>
      {subValue && (
        <p className="text-xs text-muted-foreground mt-1">{subValue}</p>
      )}
      {trend && trendValue !== undefined && (
        <div className="mt-2">
          <TrendBadge trend={trend} percentage={trendValue} />
        </div>
      )}
    </div>
  );
}

interface CustomerRowProps {
  customer: CustomerMetrics;
  rank: number;
}

function CustomerRow({ customer, rank }: CustomerRowProps) {
  return (
    <TableRow>
      <TableCell className="font-medium">
        <div className="flex items-center gap-2">
          {rank <= 3 && (
            <Crown
              className={`w-4 h-4 ${
                rank === 1
                  ? 'text-amber-500'
                  : rank === 2
                  ? 'text-gray-400'
                  : 'text-amber-700'
              }`}
            />
          )}
          <span className="text-muted-foreground">#{rank}</span>
          <span className="truncate max-w-[150px]">{customer.name}</span>
        </div>
      </TableCell>
      <TableCell className="font-semibold">
        {formatCurrency(customer.ltv)}
      </TableCell>
      <TableCell>
        <TrendBadge trend={customer.trend} percentage={customer.trendPct} />
      </TableCell>
      <TableCell>
        <Badge variant={getChurnBadgeVariant(customer.churnRisk)}>
          {formatChurnRiskLabel(customer.churnRisk)}
        </Badge>
      </TableCell>
      <TableCell className="text-right text-muted-foreground">
        {customer.orders}
      </TableCell>
    </TableRow>
  );
}

interface AtRiskRowProps {
  customer: AtRiskCustomer;
}

function AtRiskRow({ customer }: AtRiskRowProps) {
  return (
    <div className="flex items-center justify-between p-2 rounded-lg bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800">
      <div className="flex items-center gap-2">
        <AlertCircle className="w-4 h-4 text-red-600" />
        <span className="font-medium truncate max-w-[120px]">{customer.name}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">
          {customer.daysSinceOrder} Tage
        </span>
        <Badge variant="destructive" className="text-xs">
          {customer.churnScore.toFixed(0)}%
        </Badge>
      </div>
    </div>
  );
}

export function CustomerLifetimeValueWidget() {
  const [periodDays, setPeriodDays] = useState(365);

  // Real-time Widget Updates
  useWidgetSubscription('customer-ltv', {
    debounceMs: 500,
    autoInvalidate: true,
    queryKeysToInvalidate: [['dashboard-widgets', 'customer-ltv']],
  });

  const { data, isLoading, isError, error, refetch } = useQuery<
    CustomerLTVData,
    Error
  >({
    queryKey: dashboardWidgetKeys.customerLTV(periodDays),
    queryFn: () => getCustomerLTV(periodDays),
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
          <Skeleton className="h-[200px] w-full" />
        </CardContent>
      </Card>
    );
  }

  if (isError || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="w-5 h-5" />
            Kundenwert
          </CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Daten
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription className="flex items-center justify-between">
              <span>{error?.message || 'Verbindung fehlgeschlagen'}</span>
              <Button variant="ghost" size="sm" onClick={() => refetch()}>
                <RefreshCw className="w-4 h-4 mr-1" />
                Wiederholen
              </Button>
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <ErrorBoundary
      fallback={<DashboardSectionError section="Kundenwert" />}
      errorTitle="Kundenwert Fehler"
      errorDescription="Die Kundenwert-Analyse konnte nicht geladen werden."
    >
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Users className="w-5 h-5" />
                Kundenwert (LTV)
              </CardTitle>
              <CardDescription>
                {data.activeCustomers} aktive von {data.totalCustomers} Kunden
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Select
                value={periodDays.toString()}
                onValueChange={(v) => setPeriodDays(parseInt(v))}
              >
                <SelectTrigger className="w-[100px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="90">90 Tage</SelectItem>
                  <SelectItem value="180">6 Monate</SelectItem>
                  <SelectItem value="365">1 Jahr</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="ghost" size="icon" onClick={() => refetch()}>
                <RefreshCw className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {/* KPI Karten */}
          <div className="grid grid-cols-3 gap-4 mb-4">
            <KPICard
              label="Gesamt-LTV"
              value={formatCurrency(data.totalLTV)}
              icon={<Crown className="w-4 h-4 text-amber-500" />}
              trend={data.overallTrend}
              trendValue={data.trendPercentage}
            />
            <KPICard
              label="Durchschnitt"
              value={formatCurrency(data.avgLTV)}
              subValue="pro Kunde"
              icon={<Users className="w-4 h-4 text-blue-500" />}
            />
            <KPICard
              label="Churn-Risiko"
              value={`${data.avgChurnRisk.toFixed(0)}%`}
              subValue="durchschnittlich"
              icon={<AlertCircle className="w-4 h-4 text-amber-500" />}
            />
          </div>

          {/* Zwei-Spalten Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Top Kunden */}
            <div>
              <h3 className="text-sm font-medium mb-2 flex items-center gap-2">
                <Crown className="w-4 h-4 text-amber-500" />
                Top-Kunden
              </h3>
              {data.topCustomers.length > 0 ? (
                <div className="rounded-lg border overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Kunde</TableHead>
                        <TableHead>LTV</TableHead>
                        <TableHead>Trend</TableHead>
                        <TableHead>Risiko</TableHead>
                        <TableHead className="text-right">Best.</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.topCustomers.slice(0, 5).map((customer, index) => (
                        <CustomerRow
                          key={customer.id}
                          customer={customer}
                          rank={index + 1}
                        />
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <div className="text-center py-6 text-muted-foreground text-sm">
                  Keine Kundendaten vorhanden
                </div>
              )}
            </div>

            {/* Risiko-Kunden */}
            <div>
              <h3 className="text-sm font-medium mb-2 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-500" />
                Churn-Risiko
              </h3>
              {data.atRiskCustomers.length > 0 ? (
                <div className="space-y-2">
                  {data.atRiskCustomers.map((customer) => (
                    <AtRiskRow key={customer.id} customer={customer} />
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-lg border border-dashed text-center">
                  <CheckCircle className="w-8 h-8 text-green-500 mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">
                    Keine Kunden mit hohem Churn-Risiko
                  </p>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </ErrorBoundary>
  );
}

// Fehlende Imports hinzufügen
import { CheckCircle } from 'lucide-react';
