/**
 * Supplier Performance Widget
 *
 * Dashboard-Widget für Lieferanten-Performance-Metriken.
 *
 * Features:
 * - Pünktlichkeit (On-Time %)
 * - Genauigkeit (Korrekte Rechnungen %)
 * - Preistrend (Preisentwicklung)
 * - Top 5 Lieferanten-Ranking
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
import { Progress } from '@/components/ui/progress';
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
  Truck,
  CheckCircle2,
  Clock,
  BarChart3,
} from 'lucide-react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';
import {
  getSupplierPerformance,
  dashboardWidgetKeys,
  type SupplierPerformanceData,
  type SupplierMetrics,
} from '../../api/dashboard-widgets';

/**
 * Hole Farbe basierend auf Score
 */
function getScoreColor(score: number): string {
  if (score >= 90) return 'text-green-600';
  if (score >= 75) return 'text-amber-600';
  return 'text-red-600';
}

/**
 * Hole Progress-Farbe
 */
function getProgressColor(score: number): string {
  if (score >= 90) return 'bg-green-600';
  if (score >= 75) return 'bg-amber-500';
  return 'bg-red-500';
}

/**
 * Formatiere Währung kompakt
 */
function formatVolume(value: number): string {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(0)}k`;
  return value.toFixed(0);
}

interface TrendIconProps {
  direction: 'up' | 'down' | 'stable';
  value: number;
}

function TrendIcon({ direction, value }: TrendIconProps) {
  if (direction === 'up') {
    return (
      <span className="flex items-center gap-1 text-red-600 text-sm">
        <TrendingUp className="w-3 h-3" />
        +{value.toFixed(1)}%
      </span>
    );
  }
  if (direction === 'down') {
    return (
      <span className="flex items-center gap-1 text-green-600 text-sm">
        <TrendingDown className="w-3 h-3" />
        {value.toFixed(1)}%
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-muted-foreground text-sm">
      <Minus className="w-3 h-3" />
      0%
    </span>
  );
}

interface MetricCardProps {
  icon: React.ReactNode;
  label: string;
  value: number;
  unit: string;
  color: string;
}

function MetricCard({ icon, label, value, unit, color }: MetricCardProps) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
      <div className={`p-2 rounded-lg bg-background ${color}`}>{icon}</div>
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-xl font-bold">
          {value.toFixed(1)}
          <span className="text-sm font-normal text-muted-foreground">{unit}</span>
        </p>
      </div>
    </div>
  );
}

interface SupplierRowProps {
  supplier: SupplierMetrics;
  rank: number;
}

function SupplierRow({ supplier, rank }: SupplierRowProps) {
  return (
    <TableRow>
      <TableCell className="font-medium">
        <span className="text-muted-foreground mr-2">#{rank}</span>
        {supplier.name}
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <span className={getScoreColor(supplier.punctuality)}>
            {supplier.punctuality.toFixed(0)}%
          </span>
          <Progress
            value={supplier.punctuality}
            className={`w-16 h-1.5 ${getProgressColor(supplier.punctuality)}`}
          />
        </div>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <span className={getScoreColor(supplier.accuracy)}>
            {supplier.accuracy.toFixed(0)}%
          </span>
          <Progress
            value={supplier.accuracy}
            className={`w-16 h-1.5 ${getProgressColor(supplier.accuracy)}`}
          />
        </div>
      </TableCell>
      <TableCell>
        <TrendIcon direction={supplier.trendDirection} value={supplier.priceTrend} />
      </TableCell>
      <TableCell className="text-right text-muted-foreground">
        {supplier.orders}
      </TableCell>
    </TableRow>
  );
}

export function SupplierPerformanceWidget() {
  const [periodDays, setPeriodDays] = useState(90);

  // Real-time Widget Updates
  useWidgetSubscription('supplier-performance', {
    debounceMs: 500,
    autoInvalidate: true,
    queryKeysToInvalidate: [['dashboard-widgets', 'supplier-performance']],
  });

  const { data, isLoading, isError, error, refetch } = useQuery<
    SupplierPerformanceData,
    Error
  >({
    queryKey: dashboardWidgetKeys.supplierPerformance(periodDays),
    queryFn: () => getSupplierPerformance(periodDays),
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
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
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
            <Truck className="w-5 h-5" />
            Lieferanten-Performance
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
      fallback={<DashboardSectionError section="Lieferanten-Performance" />}
      errorTitle="Performance Fehler"
      errorDescription="Die Lieferanten-Performance konnte nicht geladen werden."
    >
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Truck className="w-5 h-5" />
                Lieferanten-Performance
              </CardTitle>
              <CardDescription>
                {data.activeSuppliers} aktive von {data.totalSuppliers} Lieferanten
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
                  <SelectItem value="30">30 Tage</SelectItem>
                  <SelectItem value="60">60 Tage</SelectItem>
                  <SelectItem value="90">90 Tage</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="ghost" size="icon" onClick={() => refetch()}>
                <RefreshCw className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {/* Kritische Lieferanten Warnung */}
          {data.criticalCount > 0 && (
            <Alert className="mb-4 border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/20">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <AlertDescription className="text-amber-700 dark:text-amber-400">
                {data.criticalCount} Lieferant(en) mit kritischer Performance
              </AlertDescription>
            </Alert>
          )}

          {/* Metriken-Karten */}
          <div className="grid grid-cols-3 gap-4 mb-4">
            <MetricCard
              icon={<Clock className="w-4 h-4" />}
              label="Pünktlichkeit"
              value={data.overallPunctuality}
              unit="%"
              color={getScoreColor(data.overallPunctuality)}
            />
            <MetricCard
              icon={<CheckCircle2 className="w-4 h-4" />}
              label="Genauigkeit"
              value={data.overallAccuracy}
              unit="%"
              color={getScoreColor(data.overallAccuracy)}
            />
            <MetricCard
              icon={<BarChart3 className="w-4 h-4" />}
              label="Preistrend"
              value={data.avgPriceChange}
              unit="%"
              color={
                data.avgPriceChange > 2
                  ? 'text-red-600'
                  : data.avgPriceChange < -2
                  ? 'text-green-600'
                  : 'text-muted-foreground'
              }
            />
          </div>

          {/* Top 5 Lieferanten Tabelle */}
          {data.topSuppliers.length > 0 ? (
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Lieferant</TableHead>
                    <TableHead>Pünktlichkeit</TableHead>
                    <TableHead>Genauigkeit</TableHead>
                    <TableHead>Preistrend</TableHead>
                    <TableHead className="text-right">Bestellungen</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.topSuppliers.map((supplier, index) => (
                    <SupplierRow
                      key={supplier.id}
                      supplier={supplier}
                      rank={index + 1}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              Keine Lieferantendaten im gewaehlten Zeitraum
            </div>
          )}
        </CardContent>
      </Card>
    </ErrorBoundary>
  );
}
