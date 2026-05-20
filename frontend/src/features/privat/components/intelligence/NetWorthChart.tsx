/**
 * NetWorthChart - Nettovermögen-Visualisierung
 *
 * Zeigt die Vermögensaufstellung mit:
 * - Gesamtvermögen (Assets)
 * - Gesamtschulden (Liabilities)
 * - Nettovermögen
 * - Asset-Allokation als Pie Chart
 */

import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  Home,
  Car,
  PiggyBank,
  CreditCard,
  RefreshCw,
  ArrowUp,
  ArrowDown,
  Minus,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { privatIntelligenceService } from '@/lib/api/services/privat-intelligence';
import type { NetWorthComponents } from '@/types/privat';

interface NetWorthChartProps {
  spaceId: string;
  className?: string;
  compact?: boolean;
}

const ASSET_COLORS: Record<string, string> = {
  properties: 'bg-green-500',
  vehicles: 'bg-orange-500',
  investments: 'bg-blue-500',
};

const ASSET_ICONS: Record<string, React.ReactNode> = {
  properties: <Home className="h-4 w-4" />,
  vehicles: <Car className="h-4 w-4" />,
  investments: <PiggyBank className="h-4 w-4" />,
};

const ASSET_LABELS: Record<string, string> = {
  properties: 'Immobilien',
  vehicles: 'Fahrzeuge',
  investments: 'Geldanlagen',
};

export function NetWorthChart({
  spaceId,
  className,
  compact = false,
}: NetWorthChartProps) {
  const {
    data: netWorth,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['net-worth', spaceId],
    queryFn: () => privatIntelligenceService.getNetWorth(spaceId),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const formatCurrency = (amount: number): string => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      maximumFractionDigits: 0,
    }).format(amount);
  };

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wallet className="h-5 w-5 text-red-500" />
            Nettovermögen
          </CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Daten
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (compact) {
    return (
      <CompactView
        netWorth={netWorth}
        isLoading={isLoading}
        formatCurrency={formatCurrency}
        className={className}
      />
    );
  }

  return (
    <Card className={cn('', className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Wallet className="h-5 w-5 text-green-500" />
              Nettovermögen
            </CardTitle>
            <CardDescription>Ihre Vermögensposition</CardDescription>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Nettovermögen aktualisieren"
          >
            <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} aria-hidden="true" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LoadingSkeleton />
        ) : netWorth ? (
          <div className="space-y-6">
            {/* Main Numbers */}
            <div className="grid gap-4 md:grid-cols-3">
              <div className="p-4 rounded-lg bg-green-50 dark:bg-green-950/30">
                <div className="flex items-center gap-2 mb-2">
                  <ArrowUp className="h-4 w-4 text-green-600" />
                  <span className="text-sm text-muted-foreground">Vermögen</span>
                </div>
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                  {formatCurrency(netWorth.totalAssets)}
                </p>
              </div>

              <div className="p-4 rounded-lg bg-red-50 dark:bg-red-950/30">
                <div className="flex items-center gap-2 mb-2">
                  <ArrowDown className="h-4 w-4 text-red-600" />
                  <span className="text-sm text-muted-foreground">Schulden</span>
                </div>
                <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                  {formatCurrency(netWorth.totalLiabilities)}
                </p>
              </div>

              <div
                className={cn(
                  'p-4 rounded-lg',
                  netWorth.netWorth >= 0
                    ? 'bg-blue-50 dark:bg-blue-950/30'
                    : 'bg-orange-50 dark:bg-orange-950/30'
                )}
              >
                <div className="flex items-center gap-2 mb-2">
                  <Minus className="h-4 w-4" />
                  <span className="text-sm text-muted-foreground">Netto</span>
                </div>
                <p
                  className={cn(
                    'text-2xl font-bold',
                    netWorth.netWorth >= 0
                      ? 'text-blue-600 dark:text-blue-400'
                      : 'text-orange-600 dark:text-orange-400'
                  )}
                >
                  {formatCurrency(netWorth.netWorth)}
                </p>
              </div>
            </div>

            {/* Asset Breakdown */}
            <div className="space-y-4">
              <h4 className="font-medium">Vermögensaufstellung</h4>

              {/* Visual Bar */}
              <div className="h-8 rounded-full overflow-hidden flex">
                {Object.entries(netWorth.assetAllocation).map(([key, data]) => (
                  <div
                    key={key}
                    className={cn('h-full transition-all', ASSET_COLORS[key] || 'bg-gray-400')}
                    style={{ width: `${data.percentage}%` }}
                    title={`${ASSET_LABELS[key] || key}: ${data.percentage.toFixed(1)}%`}
                  />
                ))}
              </div>

              {/* Legend */}
              <div className="grid gap-3 md:grid-cols-3">
                {Object.entries(netWorth.components).map(([key, data]) => {
                  if (key === 'loans') return null;
                  const value = 'value' in data ? data.value : 0;
                  const percentage = netWorth.assetAllocation[key]?.percentage || 0;

                  return (
                    <div
                      key={key}
                      className="flex items-center gap-3 p-3 rounded-lg bg-muted/50"
                    >
                      <div
                        className={cn(
                          'p-2 rounded-lg text-white',
                          ASSET_COLORS[key] || 'bg-gray-500'
                        )}
                      >
                        {ASSET_ICONS[key] || <Wallet className="h-4 w-4" />}
                      </div>
                      <div className="flex-1">
                        <p className="text-sm font-medium">
                          {ASSET_LABELS[key] || key}
                        </p>
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">
                            {data.count}x
                          </span>
                          <span className="text-sm font-medium">
                            {formatCurrency(value)}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {percentage.toFixed(1)}%
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Loans */}
              {netWorth.components.loans.count > 0 && (
                <div className="p-4 rounded-lg bg-red-50 dark:bg-red-950/30">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-red-500 text-white">
                      <CreditCard className="h-4 w-4" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium">Kredite</p>
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground">
                          {netWorth.components.loans.count}x
                        </span>
                        <span className="text-sm font-medium text-red-600 dark:text-red-400">
                          -{formatCurrency(netWorth.components.loans.outstanding)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Last Updated */}
            <p className="text-xs text-muted-foreground text-right">
              Berechnet am:{' '}
              {new Date(netWorth.calculatedAt).toLocaleString('de-DE')}
            </p>
          </div>
        ) : (
          <p className="text-center py-8 text-muted-foreground">
            Keine Daten verfügbar
          </p>
        )}
      </CardContent>
    </Card>
  );
}

interface CompactViewProps {
  netWorth?: NetWorthComponents;
  isLoading: boolean;
  formatCurrency: (amount: number) => string;
  className?: string;
}

function CompactView({ netWorth, isLoading, formatCurrency, className }: CompactViewProps) {
  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="p-4">
          <div className="flex items-center gap-4">
            <Skeleton className="h-12 w-12 rounded-full" />
            <div className="flex-1">
              <Skeleton className="h-4 w-32 mb-2" />
              <Skeleton className="h-6 w-24" />
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!netWorth) {
    return null;
  }

  return (
    <Card className={className}>
      <CardContent className="p-4">
        <div className="flex items-center gap-4">
          <div
            className={cn(
              'h-12 w-12 rounded-full flex items-center justify-center',
              netWorth.netWorth >= 0
                ? 'bg-green-100 dark:bg-green-950 text-green-600'
                : 'bg-red-100 dark:bg-red-950 text-red-600'
            )}
          >
            {netWorth.netWorth >= 0 ? (
              <TrendingUp className="h-6 w-6" />
            ) : (
              <TrendingDown className="h-6 w-6" />
            )}
          </div>
          <div className="flex-1">
            <span className="text-sm text-muted-foreground">Nettovermögen</span>
            <p
              className={cn(
                'text-xl font-bold',
                netWorth.netWorth >= 0
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-red-600 dark:text-red-400'
              )}
            >
              {formatCurrency(netWorth.netWorth)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-8 rounded-full" />
      <div className="grid gap-3 md:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
    </div>
  );
}

export default NetWorthChart;
