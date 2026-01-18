/**
 * Payment Behavior Dashboard
 *
 * Hauptseite fuer Zahlungsverhaltens-Analyse.
 */

import { useState } from 'react';
import { Link } from '@tanstack/react-router';
import {
  CreditCard,
  RefreshCw,
  Users,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Minus,
  Clock,
  Percent,
  DollarSign,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { usePaymentBehaviorDashboard } from '../hooks/use-payment-behavior-queries';
import type {
  PaymentMetrics,
  PaymentBehaviorCategory,
  PaymentTrend,
} from '../types/payment-behavior-types';
import {
  BEHAVIOR_CATEGORY_COLORS,
  BEHAVIOR_CATEGORY_LABELS,
  PAYMENT_TREND_COLORS,
  PAYMENT_TREND_LABELS,
  UI_LABELS,
} from '../types/payment-behavior-types';

interface PaymentBehaviorDashboardProps {
  className?: string;
}

export function PaymentBehaviorDashboard({ className }: PaymentBehaviorDashboardProps) {
  const [periodDays, setPeriodDays] = useState(365);
  const [activeTab, setActiveTab] = useState('overview');

  const { report, distribution, isLoading, isError, error, refetch } =
    usePaymentBehaviorDashboard(periodDays);

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
        <h3 className="text-lg font-medium">Fehler beim Laden</h3>
        <p className="text-sm text-muted-foreground mt-1">
          {error?.message || 'Ein unbekannter Fehler ist aufgetreten.'}
        </p>
        <Button onClick={() => refetch()} className="mt-4">
          <RefreshCw className="h-4 w-4 mr-2" />
          Erneut versuchen
        </Button>
      </div>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CreditCard className="h-7 w-7" />
            {UI_LABELS.dashboard}
          </h1>
          <p className="text-muted-foreground mt-1">
            Analyse des Kunden-Zahlungsverhaltens fuer bessere Kreditentscheidungen.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select
            value={periodDays.toString()}
            onValueChange={(v) => setPeriodDays(parseInt(v))}
          >
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Zeitraum" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="90">Letzte 90 Tage</SelectItem>
              <SelectItem value="180">Letzte 180 Tage</SelectItem>
              <SelectItem value="365">Letztes Jahr</SelectItem>
              <SelectItem value="730">Letzte 2 Jahre</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={cn('h-4 w-4 mr-2', isLoading && 'animate-spin')} />
            Aktualisieren
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard
          title="Analysierte Kunden"
          value={isLoading ? undefined : report?.analyzedCustomers}
          suffix={`/ ${report?.totalCustomers || 0}`}
          icon={Users}
          isLoading={isLoading}
        />
        <SummaryCard
          title="Durchschn. Zahldauer"
          value={isLoading ? undefined : report?.summary.avgPaymentDaysOverall.toFixed(1)}
          suffix="Tage"
          icon={Clock}
          benchmark={report?.benchmarkAvgPaymentDays}
          isLoading={isLoading}
        />
        <SummaryCard
          title="Puenktlichkeitsrate"
          value={
            isLoading
              ? undefined
              : `${(report?.summary.avgPunctualityRate || 0) * 100}`.slice(0, 4)
          }
          suffix="%"
          icon={Percent}
          isLoading={isLoading}
        />
        <SummaryCard
          title="Ueberfaelliges Volumen"
          value={isLoading ? undefined : formatCurrency(report?.summary.overdueTotal || 0)}
          icon={AlertTriangle}
          isLoading={isLoading}
          valueClassName="text-red-600 dark:text-red-400"
        />
      </div>

      {/* Category Distribution */}
      {!isLoading && distribution && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Kategorien-Verteilung</CardTitle>
            <CardDescription>
              Verteilung der Kunden nach Zahlungsverhalten
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {(
                ['excellent', 'punctual', 'delayed', 'problematic', 'defaulter'] as PaymentBehaviorCategory[]
              ).map((category) => (
                <CategoryDistributionItem
                  key={category}
                  category={category}
                  count={distribution[category]}
                  total={distribution.total}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Content Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview" className="gap-2">
            <Users className="h-4 w-4" />
            Uebersicht
          </TabsTrigger>
          <TabsTrigger value="top" className="gap-2">
            <TrendingUp className="h-4 w-4" />
            {UI_LABELS.topPayers}
          </TabsTrigger>
          <TabsTrigger value="risk" className="gap-2">
            <AlertTriangle className="h-4 w-4" />
            {UI_LABELS.highRisk}
          </TabsTrigger>
          <TabsTrigger value="trends" className="gap-2">
            <TrendingDown className="h-4 w-4" />
            Trends
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          {isLoading ? (
            <LoadingSkeleton rows={5} />
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <CustomerListCard
                title={UI_LABELS.topPayers}
                customers={report?.topPayers || []}
                emptyMessage="Keine Top-Zahler gefunden"
              />
              <CustomerListCard
                title={UI_LABELS.worstPayers}
                customers={report?.worstPayers || []}
                emptyMessage="Keine schlechten Zahler gefunden"
              />
            </div>
          )}
        </TabsContent>

        <TabsContent value="top" className="mt-4">
          {isLoading ? (
            <LoadingSkeleton rows={10} />
          ) : (
            <CustomerTable customers={report?.topPayers || []} />
          )}
        </TabsContent>

        <TabsContent value="risk" className="mt-4">
          {isLoading ? (
            <LoadingSkeleton rows={5} />
          ) : (
            <div className="space-y-4">
              <Card className="border-red-200 dark:border-red-800">
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5 text-red-600" />
                    <CardTitle className="text-lg">Risiko-Kunden</CardTitle>
                  </div>
                  <CardDescription>
                    Kunden mit hohem Ausfallrisiko (problematisch oder Zahlungsausfall)
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {report?.highRiskCustomers.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4 text-center">
                      Keine Risiko-Kunden gefunden
                    </p>
                  ) : (
                    <CustomerTable customers={report?.highRiskCustomers || []} />
                  )}
                </CardContent>
              </Card>

              {report && report.summary.volumeAtRisk > 0 && (
                <Card>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-muted-foreground">Volumen bei Risiko</p>
                        <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                          {formatCurrency(report.summary.volumeAtRisk)}
                        </p>
                      </div>
                      <div className="h-12 w-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                        <DollarSign className="h-6 w-6 text-red-600" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="trends" className="mt-4">
          {isLoading ? (
            <LoadingSkeleton rows={6} />
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <CustomerListCard
                title="Verbessernd"
                customers={report?.improvingCustomers || []}
                emptyMessage="Keine sich verbessernden Kunden"
                icon={<TrendingUp className="h-5 w-5 text-green-600" />}
              />
              <CustomerListCard
                title="Verschlechternd"
                customers={report?.decliningCustomers || []}
                emptyMessage="Keine sich verschlechternden Kunden"
                icon={<TrendingDown className="h-5 w-5 text-red-600" />}
              />
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

// =============================================================================
// Sub-Components
// =============================================================================

interface SummaryCardProps {
  title: string;
  value?: number | string;
  suffix?: string;
  icon: React.ElementType;
  isLoading?: boolean;
  valueClassName?: string;
  benchmark?: number;
}

function SummaryCard({
  title,
  value,
  suffix,
  icon: Icon,
  isLoading,
  valueClassName,
  benchmark,
}: SummaryCardProps) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            {isLoading ? (
              <Skeleton className="h-8 w-20 mt-1" />
            ) : (
              <div className="flex items-baseline gap-2 mt-1">
                <span className={cn('text-2xl font-bold', valueClassName)}>
                  {value ?? '-'}
                </span>
                {suffix && (
                  <span className="text-sm text-muted-foreground">{suffix}</span>
                )}
              </div>
            )}
            {benchmark !== undefined && !isLoading && (
              <p className="text-xs text-muted-foreground mt-1">
                Benchmark: {benchmark}
              </p>
            )}
          </div>
          <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
            <Icon className="h-6 w-6 text-primary" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface CategoryDistributionItemProps {
  category: PaymentBehaviorCategory;
  count: number;
  total: number;
}

function CategoryDistributionItem({ category, count, total }: CategoryDistributionItemProps) {
  const colors = BEHAVIOR_CATEGORY_COLORS[category];
  const percentage = total > 0 ? ((count / total) * 100).toFixed(1) : '0';

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-4 py-3 rounded-lg border',
        colors.bg,
        colors.border
      )}
    >
      <span className="text-2xl">{colors.icon}</span>
      <div>
        <p className={cn('font-medium', colors.text)}>
          {BEHAVIOR_CATEGORY_LABELS[category]}
        </p>
        <p className="text-sm text-muted-foreground">
          {count} ({percentage}%)
        </p>
      </div>
    </div>
  );
}

interface CustomerListCardProps {
  title: string;
  customers: PaymentMetrics[];
  emptyMessage: string;
  icon?: React.ReactNode;
}

function CustomerListCard({ title, customers, emptyMessage, icon }: CustomerListCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {customers.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            {emptyMessage}
          </p>
        ) : (
          <div className="space-y-3">
            {customers.slice(0, 5).map((customer) => (
              <CustomerListItem key={customer.entityId} customer={customer} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface CustomerListItemProps {
  customer: PaymentMetrics;
}

function CustomerListItem({ customer }: CustomerListItemProps) {
  const categoryColors = BEHAVIOR_CATEGORY_COLORS[customer.behaviorCategory];

  return (
    <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-xl">{categoryColors.icon}</span>
        <div className="min-w-0">
          <p className="font-medium truncate">{customer.entityName}</p>
          <div className="flex items-center gap-2 mt-1">
            <CategoryBadge category={customer.behaviorCategory} />
            <TrendIndicator trend={customer.paymentTrend} />
          </div>
        </div>
      </div>
      <div className="text-right">
        <ScoreBadge score={customer.paymentScore} />
        <p className="text-xs text-muted-foreground mt-1">
          {customer.avgPaymentDays.toFixed(0)} Tage
        </p>
      </div>
    </div>
  );
}

interface CustomerTableProps {
  customers: PaymentMetrics[];
}

function CustomerTable({ customers }: CustomerTableProps) {
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  if (customers.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        Keine Kunden gefunden
      </p>
    );
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40px]" />
            <TableHead>{UI_LABELS.customer}</TableHead>
            <TableHead>{UI_LABELS.category}</TableHead>
            <TableHead className="text-right">{UI_LABELS.score}</TableHead>
            <TableHead className="text-right">{UI_LABELS.avgDays}</TableHead>
            <TableHead className="text-right">{UI_LABELS.punctuality}</TableHead>
            <TableHead className="text-right">{UI_LABELS.overdue}</TableHead>
            <TableHead>{UI_LABELS.trend}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {customers.map((customer) => (
            <Collapsible
              key={customer.entityId}
              open={expandedRow === customer.entityId}
              onOpenChange={() =>
                setExpandedRow(
                  expandedRow === customer.entityId ? null : customer.entityId
                )
              }
              asChild
            >
              <>
                <TableRow className="cursor-pointer hover:bg-muted/50">
                  <TableCell>
                    <CollapsibleTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-6 w-6">
                        {expandedRow === customer.entityId ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </Button>
                    </CollapsibleTrigger>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="text-lg">
                        {BEHAVIOR_CATEGORY_COLORS[customer.behaviorCategory].icon}
                      </span>
                      <span className="font-medium">{customer.entityName}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <CategoryBadge category={customer.behaviorCategory} />
                  </TableCell>
                  <TableCell className="text-right">
                    <ScoreBadge score={customer.paymentScore} />
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    {customer.avgPaymentDays.toFixed(1)}
                  </TableCell>
                  <TableCell className="text-right">
                    {(customer.punctualityRate * 100).toFixed(0)}%
                  </TableCell>
                  <TableCell className="text-right">
                    {formatCurrency(customer.overdueVolume)}
                  </TableCell>
                  <TableCell>
                    <TrendIndicator trend={customer.paymentTrend} showLabel />
                  </TableCell>
                </TableRow>
                <CollapsibleContent asChild>
                  <TableRow className="bg-muted/30">
                    <TableCell colSpan={8} className="p-4">
                      <CustomerDetails customer={customer} />
                    </TableCell>
                  </TableRow>
                </CollapsibleContent>
              </>
            </Collapsible>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

interface CustomerDetailsProps {
  customer: PaymentMetrics;
}

function CustomerDetails({ customer }: CustomerDetailsProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div>
        <h4 className="text-sm font-medium mb-3">Rechnungs-Statistik</h4>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Gesamt</dt>
            <dd className="font-medium">{customer.totalInvoices}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Bezahlt</dt>
            <dd className="font-medium text-green-600">{customer.paidInvoices}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Offen</dt>
            <dd className="font-medium">{customer.unpaidInvoices}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Ueberfaellig</dt>
            <dd className="font-medium text-red-600">{customer.overdueInvoices}</dd>
          </div>
        </dl>
      </div>

      <div>
        <h4 className="text-sm font-medium mb-3">Volumen</h4>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Gesamt</dt>
            <dd className="font-medium">{formatCurrency(customer.totalVolume)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Bezahlt</dt>
            <dd className="font-medium text-green-600">
              {formatCurrency(customer.paidVolume)}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Ausstehend</dt>
            <dd className="font-medium">
              {formatCurrency(customer.outstandingVolume)}
            </dd>
          </div>
        </dl>
      </div>

      <div>
        <h4 className="text-sm font-medium mb-3">Zahlungsverhalten</h4>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Frueh-Rate</dt>
            <dd className="font-medium text-green-600">
              {(customer.earlyPaymentRate * 100).toFixed(0)}%
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Spaet-Rate</dt>
            <dd className="font-medium text-red-600">
              {(customer.latePaymentRate * 100).toFixed(0)}%
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Skonto-Nutzung</dt>
            <dd className="font-medium">
              {(customer.skontoUtilizationRate * 100).toFixed(0)}%
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Skonto gespart</dt>
            <dd className="font-medium text-green-600">
              {formatCurrency(customer.skontoSaved)}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

// =============================================================================
// Helper Components
// =============================================================================

interface CategoryBadgeProps {
  category: PaymentBehaviorCategory;
}

function CategoryBadge({ category }: CategoryBadgeProps) {
  const colors = BEHAVIOR_CATEGORY_COLORS[category];
  return (
    <Badge className={cn(colors.bg, colors.text, 'border-0')}>
      {BEHAVIOR_CATEGORY_LABELS[category]}
    </Badge>
  );
}

interface ScoreBadgeProps {
  score: number;
}

function ScoreBadge({ score }: ScoreBadgeProps) {
  let colorClass = 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
  if (score >= 80) {
    colorClass = 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
  } else if (score >= 60) {
    colorClass = 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400';
  } else if (score >= 40) {
    colorClass = 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400';
  } else {
    colorClass = 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400';
  }

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center font-bold rounded-full px-2 py-0.5 text-sm min-w-[40px]',
        colorClass
      )}
    >
      {Math.round(score)}
    </span>
  );
}

interface TrendIndicatorProps {
  trend: PaymentTrend;
  showLabel?: boolean;
}

function TrendIndicator({ trend, showLabel = false }: TrendIndicatorProps) {
  const config = {
    improving: { Icon: TrendingUp, label: 'Verbessernd' },
    stable: { Icon: Minus, label: 'Stabil' },
    declining: { Icon: TrendingDown, label: 'Verschlechternd' },
  };

  const { Icon, label } = config[trend];
  const colors = PAYMENT_TREND_COLORS[trend];

  return (
    <span className={cn('inline-flex items-center gap-1', colors.text)}>
      <Icon className="h-4 w-4" />
      {showLabel && <span className="text-xs">{label}</span>}
    </span>
  );
}

function LoadingSkeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-3">
      {[...Array(rows)].map((_, i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
    </div>
  );
}

// =============================================================================
// Helper Functions
// =============================================================================

function formatCurrency(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M EUR`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K EUR`;
  }
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value);
}
