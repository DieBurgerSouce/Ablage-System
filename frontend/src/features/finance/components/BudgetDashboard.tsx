/**
 * Budget Dashboard Komponente
 *
 * Zentrale Ansicht für Budget-Verwaltung mit:
 * - Budget-Übersicht mit Soll/Ist-Vergleich
 * - Kostenstellen-Hierarchie
 * - Abweichungsanalyse (Drill-Down)
 * - Alert-System bei Überschreitung
 *
 * Phase 2.1 der Feature-Roadmap (Januar 2026)
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  Legend,
  type TooltipProps,
} from 'recharts';
import type { ValueType, NameType } from 'recharts/types/component/DefaultTooltipContent';
import { useBudgets, useBudgetSummary, useVarianceReport, useBudgetAlerts, useAcknowledgeAlert, useActivateBudget, useCloseBudget } from '../hooks/use-budget-queries';
import type { BudgetSummary, BudgetVarianceReport, BudgetLineStatus, AlertSeverity } from '@/lib/api/services/budgets';
import { AlertTriangle, CheckCircle2, AlertCircle, TrendingUp, TrendingDown, RefreshCw, Building2, Wallet, FileText, Bell, ChevronDown, Check, Info, Target } from 'lucide-react';
import { useTheme } from '@/lib/theme/ThemeContext';

// ==================== Utility Functions ====================

function formatCurrency(value: number, currency = 'EUR'): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value / 100);
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateStr));
}

// ==================== Status Config ====================

const STATUS_CONFIG: Record<
  BudgetLineStatus,
  {
    label: string;
    icon: typeof CheckCircle2;
    color: string;
    bgColor: string;
    borderColor: string;
    textColor: string;
  }
> = {
  under_budget: {
    label: 'Unter Budget',
    icon: CheckCircle2,
    color: '#22c55e',
    bgColor: 'bg-green-50 dark:bg-green-950',
    borderColor: 'border-green-200 dark:border-green-800',
    textColor: 'text-green-700 dark:text-green-400',
  },
  on_track: {
    label: 'Im Plan',
    icon: TrendingUp,
    color: '#84cc16',
    bgColor: 'bg-lime-50 dark:bg-lime-950',
    borderColor: 'border-lime-200 dark:border-lime-800',
    textColor: 'text-lime-700 dark:text-lime-400',
  },
  warning: {
    label: 'Warnung',
    icon: AlertCircle,
    color: '#f97316',
    bgColor: 'bg-orange-50 dark:bg-orange-950',
    borderColor: 'border-orange-200 dark:border-orange-800',
    textColor: 'text-orange-700 dark:text-orange-400',
  },
  critical: {
    label: 'Kritisch',
    icon: AlertTriangle,
    color: '#ef4444',
    bgColor: 'bg-red-50 dark:bg-red-950',
    borderColor: 'border-red-200 dark:border-red-800',
    textColor: 'text-red-700 dark:text-red-400',
  },
  exceeded: {
    label: 'Überschritten',
    icon: TrendingDown,
    color: '#dc2626',
    bgColor: 'bg-red-100 dark:bg-red-900',
    borderColor: 'border-red-300 dark:border-red-700',
    textColor: 'text-red-800 dark:text-red-300',
  },
};

const ALERT_SEVERITY_CONFIG: Record<
  AlertSeverity,
  {
    label: string;
    icon: typeof Info;
    variant: 'default' | 'destructive';
    bgColor: string;
  }
> = {
  info: {
    label: 'Info',
    icon: Info,
    variant: 'default',
    bgColor: 'bg-blue-50 dark:bg-blue-950',
  },
  warning: {
    label: 'Warnung',
    icon: AlertCircle,
    variant: 'default',
    bgColor: 'bg-yellow-50 dark:bg-yellow-950',
  },
  critical: {
    label: 'Kritisch',
    icon: AlertTriangle,
    variant: 'destructive',
    bgColor: 'bg-orange-50 dark:bg-orange-950',
  },
  exceeded: {
    label: 'Überschritten',
    icon: TrendingDown,
    variant: 'destructive',
    bgColor: 'bg-red-50 dark:bg-red-950',
  },
};

// ==================== Chart Colors Hook ====================

function useChartColors() {
  const { displayMode } = useTheme();

  return useMemo(() => {
    const computedStyle = getComputedStyle(document.documentElement);
    const getColor = (varName: string, fallback: string): string => {
      const value = computedStyle.getPropertyValue(varName).trim();
      return value || fallback;
    };

    return {
      planned: getColor('--chart-1', '#3b82f6'),
      actual: getColor('--chart-2', '#22c55e'),
      warning: getColor('--chart-3', '#f97316'),
      exceeded: getColor('--chart-4', '#ef4444'),
      neutral: getColor('--muted-foreground', '#6b7280'),
    };
  }, [displayMode]);
}

// ==================== Status Badge Component ====================

function StatusBadge({ status }: { status: BudgetLineStatus }) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  return (
    <Badge variant="outline" className={`${config.bgColor} ${config.borderColor} ${config.textColor} gap-1`}>
      <Icon className="h-3 w-3" />
      {config.label}
    </Badge>
  );
}

// ==================== Utilization Bar Component ====================

function UtilizationBar({
  utilization,
  warningThreshold = 80,
  criticalThreshold = 95,
}: {
  utilization: number;
  warningThreshold?: number;
  criticalThreshold?: number;
}) {
  const getColor = () => {
    if (utilization > 100) return 'bg-red-500';
    if (utilization >= criticalThreshold) return 'bg-orange-500';
    if (utilization >= warningThreshold) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  const displayValue = Math.min(utilization, 100);

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">Auslastung</span>
        <span className={utilization > 100 ? 'text-red-600 font-medium' : ''}>
          {formatPercent(utilization)}
        </span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${getColor()} rounded-full transition-all`} style={{ width: `${displayValue}%` }} />
      </div>
    </div>
  );
}

// ==================== KPI Card Component ====================

interface KPICardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
}

function KPICard({ title, value, subtitle, icon, trend, trendValue }: KPICardProps) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold">{value}</p>
            {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
            {trend && trendValue && (
              <div
                className={`flex items-center gap-1 text-xs mt-1 ${
                  trend === 'up' ? 'text-green-600' : trend === 'down' ? 'text-red-600' : 'text-muted-foreground'
                }`}
              >
                {trend === 'up' ? <TrendingUp className="h-3 w-3" /> : trend === 'down' ? <TrendingDown className="h-3 w-3" /> : null}
                {trendValue}
              </div>
            )}
          </div>
          <div className="h-12 w-12 rounded-lg bg-muted flex items-center justify-center">{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Budget Summary Cards ====================

function BudgetSummaryCards({ summary }: { summary: BudgetSummary }) {
  const utilization = summary.utilizationPercent;
  const remaining = summary.totalRemaining;
  const isOverBudget = remaining < 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <KPICard
        title="Geplantes Budget"
        value={formatCurrency(summary.totalPlanned)}
        subtitle={summary.periodLabel}
        icon={<Target className="h-6 w-6 text-blue-500" />}
      />
      <KPICard
        title="Ist-Ausgaben"
        value={formatCurrency(summary.totalActual)}
        subtitle={`${summary.lineCount} Positionen`}
        icon={<Wallet className="h-6 w-6 text-green-500" />}
        trend={isOverBudget ? 'down' : 'up'}
        trendValue={formatPercent(utilization) + ' verbraucht'}
      />
      <KPICard
        title="Verbleibendes Budget"
        value={formatCurrency(Math.abs(remaining))}
        subtitle={isOverBudget ? 'Überschreitung' : 'Noch verfügbar'}
        icon={
          isOverBudget ? (
            <AlertTriangle className="h-6 w-6 text-red-500" />
          ) : (
            <CheckCircle2 className="h-6 w-6 text-green-500" />
          )
        }
      />
      <KPICard
        title="Offene Alerts"
        value={String(summary.unacknowledgedAlerts)}
        subtitle={`${summary.kostenstelleCount} Kostenstellen`}
        icon={<Bell className="h-6 w-6 text-orange-500" />}
      />
    </div>
  );
}

// ==================== Category Chart Component ====================

function CategoryChart({ summary }: { summary: BudgetSummary }) {
  const chartColors = useChartColors();

  const chartData = summary.byCategory.map((cat) => ({
    name: cat.category,
    planned: cat.planned,
    actual: cat.actual,
    utilization: cat.utilization,
    status: cat.status,
  }));

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const CustomTooltip = ({ active, payload, label }: TooltipProps<ValueType, NameType>) => {
    if (!active || !payload) return null;

    const data = payload[0]?.payload;
    if (!data) return null;

    return (
      <div className="rounded-lg border bg-background p-3 shadow-md">
        <p className="font-medium mb-2">{label}</p>
        <div className="space-y-1 text-sm">
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground">Geplant:</span>
            <span className="font-medium">{formatCurrency(data.planned)}</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground">Ist:</span>
            <span className="font-medium">{formatCurrency(data.actual)}</span>
          </div>
          <div className="flex justify-between gap-4 pt-1 border-t">
            <span className="text-muted-foreground">Auslastung:</span>
            <span className={`font-medium ${data.utilization > 100 ? 'text-red-600' : ''}`}>
              {formatPercent(data.utilization)}
            </span>
          </div>
        </div>
      </div>
    );
  };

  if (chartData.length === 0) {
    return (
      <div className="h-[300px] flex items-center justify-center text-muted-foreground">
        Keine Kategorie-Daten vorhanden
      </div>
    );
  }

  return (
    <div className="h-[300px]" role="img" aria-label="Budget nach Kategorien">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} tickMargin={8} angle={-45} textAnchor="end" height={60} />
          <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 12 }} tickMargin={8} />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Bar name="Geplant" dataKey="planned" fill={chartColors.planned} radius={[4, 4, 0, 0]} />
          <Bar name="Ist" dataKey="actual" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, index) => (
              <Cell
                key={index}
                fill={
                  entry.utilization > 100
                    ? chartColors.exceeded
                    : entry.utilization >= 80
                      ? chartColors.warning
                      : chartColors.actual
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ==================== Kostenstellen Distribution Chart ====================

function KostenstellenChart({ summary }: { summary: BudgetSummary }) {
  void useChartColors();

  const chartData = summary.byKostenstelle.map((ks, index) => ({
    name: ks.kostenstelleCode,
    fullName: ks.kostenstelleName,
    value: ks.actual,
    utilization: ks.utilization,
    fill: `hsl(${(index * 360) / summary.byKostenstelle.length}, 70%, 50%)`,
  }));

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.[0]) return null;

    const data = payload[0].payload;
    return (
      <div className="rounded-lg border bg-background p-3 shadow-md">
        <p className="font-medium mb-1">{data.name}</p>
        <p className="text-sm text-muted-foreground mb-2">{data.fullName}</p>
        <div className="text-sm">
          <span className="font-medium">{formatCurrency(data.value)}</span>
          <span className="text-muted-foreground ml-2">({formatPercent(data.utilization)})</span>
        </div>
      </div>
    );
  };

  if (chartData.length === 0) {
    return (
      <div className="h-[300px] flex items-center justify-center text-muted-foreground">
        Keine Kostenstellen-Daten vorhanden
      </div>
    );
  }

  return (
    <div className="h-[300px]" role="img" aria-label="Verteilung nach Kostenstellen">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={100}
            dataKey="value"
            nameKey="name"
            label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
            labelLine={false}
          >
            {chartData.map((entry, index) => (
              <Cell key={index} fill={entry.fill} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

// ==================== Variance Report Table ====================

function VarianceReportTable({ report }: { report: BudgetVarianceReport }) {
  const [sortBy, setSortBy] = useState<'variance' | 'category'>('variance');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const sortedLines = useMemo(() => {
    return [...report.lines].sort((a, b) => {
      const multiplier = sortOrder === 'asc' ? 1 : -1;
      if (sortBy === 'variance') {
        return (Math.abs(b.variance) - Math.abs(a.variance)) * multiplier;
      }
      return a.category.localeCompare(b.category) * multiplier;
    });
  }, [report.lines, sortBy, sortOrder]);

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-3 gap-4 p-4 bg-muted/30 rounded-lg">
        <div>
          <div className="text-sm text-muted-foreground">Gesamtabweichung</div>
          <div className={`text-xl font-bold ${report.totalVariance < 0 ? 'text-red-600' : 'text-green-600'}`}>
            {report.totalVariance < 0 ? '+' : ''}
            {formatCurrency(Math.abs(report.totalVariance))}
            <span className="text-sm font-normal ml-2">({formatPercent(Math.abs(report.totalVariancePercent))})</span>
          </div>
          <div className="text-xs text-muted-foreground">
            {report.totalVariance < 0 ? 'Mehr ausgegeben als geplant' : 'Weniger ausgegeben als geplant'}
          </div>
        </div>
        <div>
          <div className="text-sm text-muted-foreground">Zeitraum</div>
          <div className="text-lg font-medium">
            {formatDate(report.periodStart)} - {formatDate(report.periodEnd)}
          </div>
        </div>
        <div>
          <div className="text-sm text-muted-foreground">Positionen</div>
          <div className="text-lg font-medium">{report.lines.length} Budget-Positionen</div>
        </div>
      </div>

      {/* Recommendations */}
      {report.recommendations.length > 0 && (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Empfehlungen</AlertTitle>
          <AlertDescription>
            <ul className="list-disc list-inside space-y-1 mt-2">
              {report.recommendations.map((rec, idx) => (
                <li key={idx} className="text-sm">
                  {rec}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => {
                  if (sortBy === 'category') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                  else setSortBy('category');
                }}
              >
                Kategorie
                {sortBy === 'category' && <ChevronDown className={`inline ml-1 h-4 w-4 ${sortOrder === 'asc' ? 'rotate-180' : ''}`} />}
              </TableHead>
              <TableHead>Kostenstelle</TableHead>
              <TableHead className="text-right">Geplant</TableHead>
              <TableHead className="text-right">Ist</TableHead>
              <TableHead
                className="text-right cursor-pointer hover:bg-muted/50"
                onClick={() => {
                  if (sortBy === 'variance') setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                  else setSortBy('variance');
                }}
              >
                Abweichung
                {sortBy === 'variance' && <ChevronDown className={`inline ml-1 h-4 w-4 ${sortOrder === 'asc' ? 'rotate-180' : ''}`} />}
              </TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedLines.map((line) => (
              <TableRow key={line.lineId}>
                <TableCell>
                  <div className="font-medium">{line.category}</div>
                  {line.subcategory && <div className="text-xs text-muted-foreground">{line.subcategory}</div>}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{line.kostenstelleCode || '-'}</Badge>
                </TableCell>
                <TableCell className="text-right">{formatCurrency(line.planned)}</TableCell>
                <TableCell className="text-right">{formatCurrency(line.actual)}</TableCell>
                <TableCell className="text-right">
                  <div className={line.variance < 0 ? 'text-red-600' : 'text-green-600'}>
                    {line.variance < 0 ? '+' : '-'}
                    {formatCurrency(Math.abs(line.variance))}
                  </div>
                  <div className="text-xs text-muted-foreground">{formatPercent(Math.abs(line.variancePercent))}</div>
                </TableCell>
                <TableCell>
                  <StatusBadge status={line.status} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

// ==================== Alerts Panel Component ====================

function AlertsPanel({ budgetId }: { budgetId?: string }) {
  const { data: alerts, isLoading, error } = useBudgetAlerts({ budgetId, acknowledgedOnly: false });
  const acknowledgeMutation = useAcknowledgeAlert();

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    );
  }

  if (error || !alerts) {
    return (
      <div className="text-center py-8 text-muted-foreground">Fehler beim Laden der Alerts</div>
    );
  }

  const unacknowledged = alerts.filter((a) => !a.isAcknowledged);

  if (unacknowledged.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <CheckCircle2 className="h-12 w-12 mx-auto mb-4 text-green-500" />
        <p>Keine offenen Alerts</p>
        <p className="text-sm">Alle Budget-Warnungen wurden bearbeitet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {unacknowledged.map((alert) => {
        const config = ALERT_SEVERITY_CONFIG[alert.severity];
        const Icon = config.icon;

        return (
          <Alert key={alert.id} variant={config.variant} className={config.bgColor}>
            <Icon className="h-4 w-4" />
            <AlertTitle className="flex items-center justify-between">
              <span>{config.label}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => acknowledgeMutation.mutate(alert.id)}
                disabled={acknowledgeMutation.isPending}
              >
                {acknowledgeMutation.isPending ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Check className="h-4 w-4" />
                )}
                Bestätigen
              </Button>
            </AlertTitle>
            <AlertDescription className="mt-2">
              <p>{alert.message}</p>
              <div className="flex gap-4 mt-2 text-sm">
                <span>Schwelle: {formatPercent(alert.thresholdPercent)}</span>
                <span>Aktuell: {formatPercent(alert.actualPercent)}</span>
                <span className="text-muted-foreground">{formatDate(alert.createdAt)}</span>
              </div>
            </AlertDescription>
          </Alert>
        );
      })}
    </div>
  );
}

// ==================== Recent Allocations List ====================

function RecentAllocationsList({ allocations }: { allocations: BudgetSummary['recentAllocations'] }) {
  if (allocations.length === 0) {
    return <div className="text-center py-4 text-muted-foreground text-sm">Keine aktuellen Zuweisungen</div>;
  }

  const sourceLabels: Record<string, string> = {
    manual: 'Manuell',
    ocr_auto: 'OCR Auto',
    import: 'Import',
    rule_based: 'Regel',
  };

  return (
    <div className="space-y-2">
      {allocations.map((alloc) => (
        <div key={alloc.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/30">
          <div className="flex items-center gap-3">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <div>
              <div className="text-sm font-medium">{alloc.category}</div>
              <div className="text-xs text-muted-foreground">
                {alloc.documentName || 'Keine Dokumentreferenz'}
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="font-medium">{formatCurrency(alloc.amount)}</div>
            <div className="text-xs text-muted-foreground">
              <Badge variant="outline" className="text-xs">
                {sourceLabels[alloc.source] || alloc.source}
              </Badge>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ==================== Budget Selector Component ====================

interface BudgetSelectorProps {
  selectedBudgetId: string | null;
  onSelect: (budgetId: string) => void;
}

function BudgetSelector({ selectedBudgetId, onSelect }: BudgetSelectorProps) {
  const { data, isLoading } = useBudgets({ status: 'active' });

  if (isLoading) {
    return <Skeleton className="h-10 w-[250px]" />;
  }

  const budgets = data?.items ?? [];

  if (budgets.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        Keine aktiven Budgets vorhanden
      </div>
    );
  }

  return (
    <Select value={selectedBudgetId ?? 'none'} onValueChange={onSelect}>
      <SelectTrigger className="w-[250px]">
        <SelectValue placeholder="Budget auswählen" />
      </SelectTrigger>
      <SelectContent>
        {budgets.map((budget) => (
          <SelectItem key={budget.id} value={budget.id}>
            {budget.name} ({budget.year})
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// ==================== Main Budget Dashboard Component ====================

export interface BudgetDashboardProps {
  initialBudgetId?: string;
}

export function BudgetDashboard({ initialBudgetId }: BudgetDashboardProps) {
  const [selectedBudgetId, setSelectedBudgetId] = useState<string | null>(initialBudgetId ?? null);
  const [activeTab, setActiveTab] = useState('overview');

  // Data fetching
  const {
    data: summary,
    isLoading: summaryLoading,
    error: summaryError,
    refetch: refetchSummary,
  } = useBudgetSummary(selectedBudgetId ?? '');

  const {
    data: varianceReport,
    isLoading: varianceLoading,
  } = useVarianceReport(selectedBudgetId ?? '');

  // Actions
  const activateMutation = useActivateBudget();
  const closeMutation = useCloseBudget();

  // Loading state
  if (summaryLoading && selectedBudgetId) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-10 w-[250px]" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <Skeleton className="h-[400px]" />
      </div>
    );
  }

  // No budget selected
  if (!selectedBudgetId) {
    return (
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Wallet className="h-5 w-5" />
              Budget-Verwaltung
            </CardTitle>
            <CardDescription>Wählen Sie ein Budget aus, um Details anzuzeigen</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Building2 className="h-16 w-16 text-muted-foreground mb-4" />
            <p className="text-lg font-medium mb-4">Kein Budget ausgewählt</p>
            <BudgetSelector selectedBudgetId={selectedBudgetId} onSelect={setSelectedBudgetId} />
          </CardContent>
        </Card>
      </div>
    );
  }

  // Error state
  if (summaryError || !summary) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-bold">Budget-Dashboard</h2>
          <BudgetSelector selectedBudgetId={selectedBudgetId} onSelect={setSelectedBudgetId} />
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
            <p className="text-lg font-medium mb-2">Fehler beim Laden des Budgets</p>
            <p className="text-muted-foreground mb-4">Die Budget-Daten konnten nicht geladen werden.</p>
            <Button variant="outline" onClick={() => refetchSummary()}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Erneut versuchen
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <Wallet className="h-6 w-6" />
            {summary.budgetName}
          </h2>
          <p className="text-muted-foreground">{summary.periodLabel}</p>
        </div>
        <div className="flex items-center gap-4">
          <BudgetSelector selectedBudgetId={selectedBudgetId} onSelect={setSelectedBudgetId} />
          {summary.status === 'draft' && (
            <Button
              onClick={() => activateMutation.mutate(selectedBudgetId)}
              disabled={activateMutation.isPending}
            >
              {activateMutation.isPending && <RefreshCw className="h-4 w-4 mr-2 animate-spin" />}
              Budget aktivieren
            </Button>
          )}
          {summary.status === 'active' && (
            <Button
              variant="secondary"
              onClick={() => closeMutation.mutate(selectedBudgetId)}
              disabled={closeMutation.isPending}
            >
              {closeMutation.isPending && <RefreshCw className="h-4 w-4 mr-2 animate-spin" />}
              Budget abschließen
            </Button>
          )}
        </div>
      </div>

      {/* Alerts Banner */}
      {summary.unacknowledgedAlerts > 0 && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>
            {summary.unacknowledgedAlerts} offene{summary.unacknowledgedAlerts === 1 ? 'r' : ''} Alert
            {summary.unacknowledgedAlerts === 1 ? '' : 's'}
          </AlertTitle>
          <AlertDescription>
            Es gibt Budget-Warnungen, die Ihre Aufmerksamkeit erfordern.
          </AlertDescription>
        </Alert>
      )}

      {/* KPI Cards */}
      <BudgetSummaryCards summary={summary} />

      {/* Main Content */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview">Übersicht</TabsTrigger>
          <TabsTrigger value="variance">Abweichungsanalyse</TabsTrigger>
          <TabsTrigger value="alerts">
            Alerts
            {summary.unacknowledgedAlerts > 0 && (
              <Badge variant="destructive" className="ml-2">
                {summary.unacknowledgedAlerts}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="allocations">Zuweisungen</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Category Chart */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Budget nach Kategorien</CardTitle>
                <CardDescription>Soll/Ist-Vergleich pro Kategorie</CardDescription>
              </CardHeader>
              <CardContent>
                <CategoryChart summary={summary} />
              </CardContent>
            </Card>

            {/* Kostenstellen Distribution */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Verteilung nach Kostenstellen</CardTitle>
                <CardDescription>Ist-Ausgaben pro Kostenstelle</CardDescription>
              </CardHeader>
              <CardContent>
                <KostenstellenChart summary={summary} />
              </CardContent>
            </Card>
          </div>

          {/* Category Details Table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Kategorie-Details</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Kategorie</TableHead>
                    <TableHead className="text-right">Geplant</TableHead>
                    <TableHead className="text-right">Ist</TableHead>
                    <TableHead>Auslastung</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {summary.byCategory.map((cat) => (
                    <TableRow key={cat.category}>
                      <TableCell className="font-medium">{cat.category}</TableCell>
                      <TableCell className="text-right">{formatCurrency(cat.planned)}</TableCell>
                      <TableCell className="text-right">{formatCurrency(cat.actual)}</TableCell>
                      <TableCell className="w-[150px]">
                        <UtilizationBar utilization={cat.utilization} />
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={cat.status} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Variance Analysis Tab */}
        <TabsContent value="variance" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Abweichungsanalyse</CardTitle>
              <CardDescription>Detaillierte Soll/Ist-Vergleiche mit Drill-Down</CardDescription>
            </CardHeader>
            <CardContent>
              {varianceLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-32" />
                  <Skeleton className="h-64" />
                </div>
              ) : varianceReport ? (
                <VarianceReportTable report={varianceReport} />
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  Keine Abweichungsdaten verfügbar
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Alerts Tab */}
        <TabsContent value="alerts" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Budget-Alerts</CardTitle>
              <CardDescription>Warnungen und Benachrichtigungen bei Budgetüberschreitung</CardDescription>
            </CardHeader>
            <CardContent>
              <AlertsPanel budgetId={selectedBudgetId} />
            </CardContent>
          </Card>
        </TabsContent>

        {/* Allocations Tab */}
        <TabsContent value="allocations" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Aktuelle Zuweisungen</CardTitle>
              <CardDescription>Letzte Budget-Zuweisungen und deren Quellen</CardDescription>
            </CardHeader>
            <CardContent>
              <RecentAllocationsList allocations={summary.recentAllocations} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
