/**
 * Holding Dashboard
 *
 * Hauptseite für die Multi-Company Holding-Sicht mit konsolidierten KPIs.
 */

import { useState, useMemo } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { RefreshCcw, Building2, TrendingUp, ArrowLeftRight, Wallet } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import {
  useHoldingOverview,
  useHoldingCompanies,
  useCompanyComparison,
  useCashFlowOverview,
  holdingKeys,
} from './hooks/use-holding';
import { HoldingStatsCards } from './components/HoldingStatsCards';
import { FinancialsCard } from './components/FinancialsCard';
import { CompanyComparisonChart } from './components/CompanyComparisonChart';
import { CashFlowChart } from './components/CashFlowChart';
import { IntercompanyCard } from './components/IntercompanyCard';
import { CompanySelector } from './components/CompanySelector';
import type { ComparisonMetric, CashFlowPeriod } from './api/holding-api';

export function HoldingDashboard() {
  const queryClient = useQueryClient();

  // State
  const [selectedCompanyIds, setSelectedCompanyIds] = useState<string[]>([]);
  const [comparisonMetric, setComparisonMetric] = useState<ComparisonMetric>('receivables');
  const [cashFlowPeriod, setCashFlowPeriod] = useState<CashFlowPeriod>('monthly');

  // Effective company IDs (empty = all)
  const effectiveIds = useMemo(
    () => (selectedCompanyIds.length > 0 ? selectedCompanyIds : undefined),
    [selectedCompanyIds]
  );

  // Queries
  const { data: companies, isLoading: companiesLoading } = useHoldingCompanies();
  const {
    data: overview,
    isLoading: overviewLoading,
    error: overviewError,
  } = useHoldingOverview(effectiveIds);
  const { data: comparison, isLoading: comparisonLoading } = useCompanyComparison(
    comparisonMetric,
    effectiveIds,
    !!overview && overview.company_count > 1
  );
  const { data: cashflow, isLoading: cashflowLoading } = useCashFlowOverview(
    cashFlowPeriod,
    effectiveIds
  );

  // Refresh all data
  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: holdingKeys.all });
  };

  // Error state
  if (overviewError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Fehler beim Laden</AlertTitle>
        <AlertDescription>
          Die Holding-Daten konnten nicht geladen werden.
          {overviewError instanceof Error ? ` ${overviewError.message}` : ''}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Building2 className="h-6 w-6" />
            Holding-Dashboard
          </h1>
          <p className="text-muted-foreground">
            Konsolidierte Übersicht über alle Firmen
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          {!companiesLoading && companies && (
            <CompanySelector
              companies={companies}
              selectedIds={selectedCompanyIds}
              onSelectionChange={setSelectedCompanyIds}
            />
          )}
          <Button variant="outline" size="icon" onClick={handleRefresh}>
            <RefreshCcw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      {overviewLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : overview ? (
        <HoldingStatsCards overview={overview} />
      ) : null}

      {/* Tabs */}
      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview" className="gap-2">
            <TrendingUp className="h-4 w-4" />
            Übersicht
          </TabsTrigger>
          <TabsTrigger value="comparison" className="gap-2">
            <Building2 className="h-4 w-4" />
            Vergleich
          </TabsTrigger>
          <TabsTrigger value="cashflow" className="gap-2">
            <Wallet className="h-4 w-4" />
            Cashflow
          </TabsTrigger>
          <TabsTrigger value="intercompany" className="gap-2">
            <ArrowLeftRight className="h-4 w-4" />
            Intercompany
          </TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid lg:grid-cols-2 gap-6">
            {/* Financials */}
            {overviewLoading ? (
              <Skeleton className="h-[400px]" />
            ) : overview ? (
              <FinancialsCard financials={overview.financials} />
            ) : null}

            {/* Intercompany (Preview) */}
            {overviewLoading ? (
              <Skeleton className="h-[400px]" />
            ) : overview ? (
              <IntercompanyCard intercompany={overview.intercompany} />
            ) : null}
          </div>

          {/* Comparison Chart (if multiple companies) */}
          {overview && overview.company_count > 1 && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">Firmenvergleich</h2>
                <Select
                  value={comparisonMetric}
                  onValueChange={(v) => setComparisonMetric(v as ComparisonMetric)}
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="receivables">Forderungen</SelectItem>
                    <SelectItem value="payables">Verbindlichkeiten</SelectItem>
                    <SelectItem value="balance">Kontostand</SelectItem>
                    <SelectItem value="documents">Dokumente</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {comparisonLoading ? (
                <Skeleton className="h-[350px]" />
              ) : comparison ? (
                <CompanyComparisonChart comparison={comparison} />
              ) : null}
            </div>
          )}
        </TabsContent>

        {/* Comparison Tab */}
        <TabsContent value="comparison" className="space-y-4">
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground">Metrik:</span>
            <Select
              value={comparisonMetric}
              onValueChange={(v) => setComparisonMetric(v as ComparisonMetric)}
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="receivables">Forderungen</SelectItem>
                <SelectItem value="payables">Verbindlichkeiten</SelectItem>
                <SelectItem value="balance">Kontostand</SelectItem>
                <SelectItem value="documents">Dokumente</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {comparisonLoading ? (
            <Skeleton className="h-[400px]" />
          ) : comparison ? (
            <CompanyComparisonChart comparison={comparison} />
          ) : (
            <Alert>
              <AlertDescription>
                Wählen Sie mindestens zwei Firmen für einen Vergleich aus.
              </AlertDescription>
            </Alert>
          )}
        </TabsContent>

        {/* Cashflow Tab */}
        <TabsContent value="cashflow" className="space-y-4">
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground">Zeitraum:</span>
            <Select
              value={cashFlowPeriod}
              onValueChange={(v) => setCashFlowPeriod(v as CashFlowPeriod)}
            >
              <SelectTrigger className="w-[150px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="daily">Heute</SelectItem>
                <SelectItem value="weekly">Diese Woche</SelectItem>
                <SelectItem value="monthly">Dieser Monat</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {cashflowLoading ? (
            <Skeleton className="h-[400px]" />
          ) : cashflow ? (
            <CashFlowChart cashflow={cashflow} />
          ) : null}
        </TabsContent>

        {/* Intercompany Tab */}
        <TabsContent value="intercompany" className="space-y-4">
          {overviewLoading ? (
            <Skeleton className="h-[400px]" />
          ) : overview ? (
            <div className="max-w-lg">
              <IntercompanyCard intercompany={overview.intercompany} />
            </div>
          ) : null}
          <Alert>
            <AlertDescription>
              Intercompany-Transaktionen werden automatisch erkannt wenn Rechnungen
              zwischen Firmen der Holding ausgestellt werden. Diese Beträge müssen
              bei der Konzernkonsolidierung eliminiert werden.
            </AlertDescription>
          </Alert>
        </TabsContent>
      </Tabs>
    </div>
  );
}
