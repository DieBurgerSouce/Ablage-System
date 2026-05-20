/**
 * CompanyDashboardPage - Multi-Firma Dashboard
 *
 * Features:
 * - Übersicht aller Firmen-Metriken
 * - Health Score Visualisierung
 * - Alerts für kritische Situationen
 * - Firmen-Vergleich mit Charts
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
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
  Building2,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  AlertCircle,
  FileText,
  Users,
  DollarSign,
  Clock,
  RefreshCw,
  BarChart3,
} from 'lucide-react';
import {
  useCompanyDashboard,
  useCompanyComparison,
} from './api/companies-admin-api';
import type {
  CompanyMetrics,
  DashboardAlert,
} from '@/lib/api/services/companies';

// ==================== Hilfsfunktionen ====================

/**
 * Formatiert einen Betrag als Währung
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
 * Formatiert eine Zahl mit Tausendertrennzeichen
 */
function formatNumber(value: number): string {
  return new Intl.NumberFormat('de-DE').format(value);
}

/**
 * Gibt die Farbe für einen Health Score zurück
 */
function getHealthScoreColor(score: number): string {
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  if (score >= 40) return 'text-orange-600';
  return 'text-red-600';
}

/**
 * Gibt die Progress-Farbe für einen Health Score zurück
 */
function getHealthScoreProgressColor(score: number): string {
  if (score >= 80) return 'bg-green-500';
  if (score >= 60) return 'bg-yellow-500';
  if (score >= 40) return 'bg-orange-500';
  return 'bg-red-500';
}

// ==================== Sub-Komponenten ====================

/**
 * Summary-Karte für eine einzelne Metrik
 */
function SummaryCard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  trend?: 'up' | 'down' | null;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between">
          <div className="text-2xl font-bold">{value}</div>
          {trend && (
            <div
              className={`flex items-center ${
                trend === 'up' ? 'text-green-600' : 'text-red-600'
              }`}
            >
              {trend === 'up' ? (
                <TrendingUp className="h-4 w-4" />
              ) : (
                <TrendingDown className="h-4 w-4" />
              )}
            </div>
          )}
        </div>
        {subtitle && (
          <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Alert-Banner für kritische Meldungen
 */
function AlertBanner({ alerts }: { alerts: DashboardAlert[] }) {
  if (alerts.length === 0) return null;

  const criticalAlerts = alerts.filter((a) => a.type === 'critical');
  const warningAlerts = alerts.filter((a) => a.type === 'warning');

  return (
    <div className="space-y-2">
      {criticalAlerts.map((alert, index) => (
        <div
          key={`critical-${index}`}
          className="flex items-center gap-3 p-3 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg"
        >
          <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0" />
          <div className="flex-1">
            <span className="font-medium text-red-900 dark:text-red-100">
              {alert.company_name}:
            </span>{' '}
            <span className="text-red-800 dark:text-red-200">
              {alert.message}
            </span>
          </div>
        </div>
      ))}
      {warningAlerts.slice(0, 3).map((alert, index) => (
        <div
          key={`warning-${index}`}
          className="flex items-center gap-3 p-3 bg-yellow-50 dark:bg-yellow-950 border border-yellow-200 dark:border-yellow-800 rounded-lg"
        >
          <AlertTriangle className="h-5 w-5 text-yellow-600 flex-shrink-0" />
          <div className="flex-1">
            <span className="font-medium text-yellow-900 dark:text-yellow-100">
              {alert.company_name}:
            </span>{' '}
            <span className="text-yellow-800 dark:text-yellow-200">
              {alert.message}
            </span>
          </div>
        </div>
      ))}
      {warningAlerts.length > 3 && (
        <p className="text-sm text-muted-foreground pl-8">
          +{warningAlerts.length - 3} weitere Warnungen
        </p>
      )}
    </div>
  );
}

/**
 * Tabelle mit Firmen-Metriken
 */
function CompanyMetricsTable({ companies }: { companies: CompanyMetrics[] }) {
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[200px]">Firma</TableHead>
            <TableHead className="text-center">Health</TableHead>
            <TableHead className="text-right">Dokumente</TableHead>
            <TableHead className="text-right">Rechnungen</TableHead>
            <TableHead className="text-right">Offen</TableHead>
            <TableHead className="text-right">Überfällig</TableHead>
            <TableHead className="text-center">Mahnungen</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {companies.map((company) => (
            <TableRow key={company.company_id}>
              <TableCell>
                <div className="flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="font-medium">
                      {company.company_short_name || company.company_name}
                    </div>
                    {company.company_short_name && (
                      <div className="text-xs text-muted-foreground">
                        {company.company_name}
                      </div>
                    )}
                  </div>
                  {!company.is_active && (
                    <Badge variant="secondary" className="text-xs">
                      Inaktiv
                    </Badge>
                  )}
                </div>
              </TableCell>
              <TableCell>
                <div className="flex flex-col items-center gap-1">
                  <span
                    className={`font-bold ${getHealthScoreColor(
                      company.health_score
                    )}`}
                  >
                    {company.health_score}
                  </span>
                  <div className="w-16">
                    <Progress
                      value={company.health_score}
                      className="h-1.5"
                      indicatorClassName={getHealthScoreProgressColor(
                        company.health_score
                      )}
                    />
                  </div>
                </div>
              </TableCell>
              <TableCell className="text-right">
                <div>{formatNumber(company.documents.total)}</div>
                <div className="text-xs text-muted-foreground">
                  {company.documents.growth_percent >= 0 ? '+' : ''}
                  {company.documents.growth_percent.toFixed(0)}% gg. Vormonat
                </div>
              </TableCell>
              <TableCell className="text-right">
                <div>{formatNumber(company.invoices.total)}</div>
                <div className="text-xs text-muted-foreground">
                  {formatCurrency(company.invoices.total_amount)}
                </div>
              </TableCell>
              <TableCell className="text-right">
                <div className="font-medium">
                  {formatCurrency(company.invoices.outstanding_amount)}
                </div>
              </TableCell>
              <TableCell className="text-right">
                {company.invoices.overdue_count > 0 ? (
                  <div className="text-red-600">
                    <div className="font-medium">
                      {company.invoices.overdue_count} ({formatCurrency(company.invoices.overdue_amount)})
                    </div>
                  </div>
                ) : (
                  <span className="text-green-600">-</span>
                )}
              </TableCell>
              <TableCell className="text-center">
                {company.dunning.active > 0 ? (
                  <div className="flex items-center justify-center gap-1">
                    <Badge
                      variant={
                        company.dunning.by_level['3'] +
                          company.dunning.by_level['4'] >
                        0
                          ? 'destructive'
                          : 'secondary'
                      }
                    >
                      {company.dunning.active}
                    </Badge>
                    {(company.dunning.by_level['3'] > 0 ||
                      company.dunning.by_level['4'] > 0) && (
                      <span className="text-xs text-red-600">
                        ({company.dunning.by_level['3']}+{company.dunning.by_level['4']} krit.)
                      </span>
                    )}
                  </div>
                ) : (
                  <span className="text-green-600">-</span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/**
 * Einfaches Balkendiagramm für Vergleiche
 */
function ComparisonChart({
  data,
  metricLabel,
}: {
  data: Array<{ company_name: string; company_short_name: string | null; value: number }>;
  metricLabel: string;
}) {
  const maxValue = Math.max(...data.map((d) => d.value), 1);

  return (
    <div className="space-y-3">
      {data.map((item, index) => (
        <div key={index} className="space-y-1">
          <div className="flex justify-between text-sm">
            <span className="font-medium">
              {item.company_short_name || item.company_name}
            </span>
            <span className="text-muted-foreground">
              {metricLabel === 'Health Score'
                ? item.value
                : formatCurrency(item.value)}
            </span>
          </div>
          <div className="w-full bg-muted rounded-full h-2">
            <div
              className="bg-primary rounded-full h-2 transition-all"
              style={{ width: `${(item.value / maxValue) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// ==================== Hauptkomponente ====================

export function CompanyDashboardPage() {
  const [selectedMetric, setSelectedMetric] = useState('invoices');

  // Daten laden
  const {
    data: dashboardData,
    isLoading,
    refetch,
  } = useCompanyDashboard({ include_inactive: false });

  const { data: comparisonData, isLoading: isLoadingComparison } =
    useCompanyComparison(selectedMetric);

  // Sortierte Firmen nach Health Score
  const sortedCompanies = useMemo(() => {
    if (!dashboardData?.companies) return [];
    return [...dashboardData.companies].sort(
      (a, b) => a.health_score - b.health_score
    );
  }, [dashboardData?.companies]);

  // Loading State
  if (isLoading) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex justify-between items-center">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-10 w-32" />
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  const summary = dashboardData?.summary;
  const alerts = dashboardData?.alerts ?? [];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">Multi-Firma Dashboard</h1>
          <p className="text-muted-foreground">
            Übersicht aller {summary?.active_companies ?? 0} aktiven Firmen
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Aktualisieren
        </Button>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-600" />
              Warnungen ({alerts.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <AlertBanner alerts={alerts} />
          </CardContent>
        </Card>
      )}

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          title="Firmen"
          value={summary?.active_companies ?? 0}
          subtitle={`von ${summary?.total_companies ?? 0} gesamt`}
          icon={Building2}
        />
        <SummaryCard
          title="Dokumente"
          value={formatNumber(summary?.total_documents ?? 0)}
          icon={FileText}
        />
        <SummaryCard
          title="Offene Forderungen"
          value={formatCurrency(summary?.total_outstanding_amount ?? 0)}
          subtitle={`${formatCurrency(summary?.total_overdue_amount ?? 0)} überfällig`}
          icon={DollarSign}
          trend={
            (summary?.total_overdue_amount ?? 0) > 0 ? 'down' : null
          }
        />
        <SummaryCard
          title="Aktive Mahnungen"
          value={summary?.active_dunnings ?? 0}
          icon={Clock}
          trend={(summary?.active_dunnings ?? 0) > 5 ? 'down' : null}
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Firmen-Tabelle (2/3) */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">
                Firmen nach Health Score
              </CardTitle>
            </CardHeader>
            <CardContent>
              {sortedCompanies.length > 0 ? (
                <CompanyMetricsTable companies={sortedCompanies} />
              ) : (
                <p className="text-muted-foreground text-center py-8">
                  Keine Firmen gefunden
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Vergleichs-Chart (1/3) */}
        <div>
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg flex items-center gap-2">
                  <BarChart3 className="h-5 w-5" />
                  Vergleich
                </CardTitle>
                <Select
                  value={selectedMetric}
                  onValueChange={setSelectedMetric}
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="invoices">Rechnungsvolumen</SelectItem>
                    <SelectItem value="outstanding">Offene Forderungen</SelectItem>
                    <SelectItem value="overdue">Überfällige</SelectItem>
                    <SelectItem value="documents">Dokumente</SelectItem>
                    <SelectItem value="entities">Geschäftspartner</SelectItem>
                    <SelectItem value="health">Health Score</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent>
              {isLoadingComparison ? (
                <div className="space-y-3">
                  {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} className="h-8" />
                  ))}
                </div>
              ) : comparisonData?.data && comparisonData.data.length > 0 ? (
                <ComparisonChart
                  data={comparisonData.data.slice(0, 8)}
                  metricLabel={comparisonData.metric_label}
                />
              ) : (
                <p className="text-muted-foreground text-center py-8">
                  Keine Vergleichsdaten verfügbar
                </p>
              )}
            </CardContent>
          </Card>

          {/* Quick Stats */}
          <Card className="mt-6">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center gap-2">
                <Users className="h-5 w-5" />
                Geschäftspartner
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Gesamt</span>
                  <span className="font-medium">
                    {formatNumber(summary?.total_entities ?? 0)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Rechnungen</span>
                  <span className="font-medium">
                    {formatNumber(summary?.total_invoices ?? 0)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default CompanyDashboardPage;
