/**
 * Risk Dashboard Component
 *
 * Haupt-Dashboard fuer das Risk Scoring System.
 */

import { useState } from 'react';
import {
  AlertTriangle,
  Users,
  Package,
  RefreshCw,
  TrendingUp,
  Loader2,
  Filter,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { RiskScoreGauge } from './RiskScoreGauge';
import { HighRiskEntitiesTable } from './HighRiskEntitiesTable';
import { RiskTrendChart, RiskDistributionChart } from './RiskTrendChart';
import { FactorContributionChart } from './RiskFactorBreakdown';
import {
  useRiskDashboard,
  useRiskMutations,
  useEntitiesWithRisk,
} from '../hooks/use-risk-queries';
import type { EntityType, RiskLevel } from '../types/risk-types';
import { UI_LABELS, RISK_LEVEL_LABELS, RISK_FACTOR_LABELS } from '../types/risk-types';

interface RiskDashboardProps {
  className?: string;
}

export function RiskDashboard({ className }: RiskDashboardProps) {
  const [entityTypeFilter, setEntityTypeFilter] = useState<EntityType | 'all'>('all');
  const [riskLevelFilter, setRiskLevelFilter] = useState<RiskLevel | 'all'>('all');
  const [recalculatingEntity, setRecalculatingEntity] = useState<string | null>(null);

  const entityType = entityTypeFilter === 'all' ? undefined : entityTypeFilter;
  const {
    statistics,
    highRiskEntities,
    isLoading,
    isError,
    error,
    refetch,
  } = useRiskDashboard(entityType);

  const { calculateEntityRisk, calculateAllRisks } = useRiskMutations();

  // Filtered entities list
  const { data: filteredEntitiesData, isLoading: isLoadingFiltered } = useEntitiesWithRisk({
    entityType,
    riskLevel: riskLevelFilter === 'all' ? undefined : riskLevelFilter,
    sortBy: 'risk_score',
    sortOrder: 'desc',
    perPage: 50,
  });

  const handleRecalculateEntity = async (entityId: string) => {
    setRecalculatingEntity(entityId);
    try {
      await calculateEntityRisk.mutateAsync(entityId);
      toast.success(UI_LABELS.successRecalculate);
    } catch {
      toast.error(UI_LABELS.errorRecalculate);
    } finally {
      setRecalculatingEntity(null);
    }
  };

  const handleRecalculateAll = async () => {
    try {
      const result = await calculateAllRisks.mutateAsync({ entityType });
      toast.success(
        `${result.updated} von ${result.processed} Entities aktualisiert`
      );
      if (result.errors > 0) {
        toast.warning(`${result.errors} Fehler bei der Berechnung`);
      }
    } catch {
      toast.error(UI_LABELS.errorRecalculate);
    }
  };

  if (isError) {
    return (
      <div className={cn('flex flex-col items-center justify-center py-12', className)}>
        <AlertTriangle className="h-16 w-16 text-destructive/50 mb-4" />
        <h2 className="text-xl font-semibold text-destructive">
          {UI_LABELS.errorLoad}
        </h2>
        <p className="text-muted-foreground mt-1">
          {error instanceof Error ? error.message : 'Ein Fehler ist aufgetreten'}
        </p>
        <Button variant="outline" onClick={() => refetch()} className="mt-4">
          Erneut versuchen
        </Button>
      </div>
    );
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header with Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-4">
          {/* Entity Type Filter */}
          <Select
            value={entityTypeFilter}
            onValueChange={(value) => setEntityTypeFilter(value as EntityType | 'all')}
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder={UI_LABELS.filterByType} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{UI_LABELS.allTypes}</SelectItem>
              <SelectItem value="customer">
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4" />
                  {UI_LABELS.customers}
                </div>
              </SelectItem>
              <SelectItem value="supplier">
                <div className="flex items-center gap-2">
                  <Package className="h-4 w-4" />
                  {UI_LABELS.suppliers}
                </div>
              </SelectItem>
            </SelectContent>
          </Select>

          {/* Risk Level Filter */}
          <Select
            value={riskLevelFilter}
            onValueChange={(value) => setRiskLevelFilter(value as RiskLevel | 'all')}
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder={UI_LABELS.filterByLevel} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{UI_LABELS.allLevels}</SelectItem>
              <SelectItem value="low">{RISK_LEVEL_LABELS.low}</SelectItem>
              <SelectItem value="medium">{RISK_LEVEL_LABELS.medium}</SelectItem>
              <SelectItem value="high">{RISK_LEVEL_LABELS.high}</SelectItem>
              <SelectItem value="critical">{RISK_LEVEL_LABELS.critical}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button
          onClick={handleRecalculateAll}
          disabled={calculateAllRisks.isPending}
        >
          {calculateAllRisks.isPending ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-2" />
          )}
          {UI_LABELS.recalculateAll}
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard
          title={UI_LABELS.totalEntities}
          value={statistics?.totalEntities ?? 0}
          icon={Users}
          isLoading={isLoading}
        />
        <SummaryCard
          title={UI_LABELS.highRiskEntities}
          value={statistics?.highRiskCount ?? 0}
          icon={AlertTriangle}
          variant="destructive"
          isLoading={isLoading}
        />
        <SummaryCard
          title={UI_LABELS.averageScore}
          value={statistics?.averageRiskScore?.toFixed(1) ?? '0.0'}
          icon={TrendingUp}
          isLoading={isLoading}
        />
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {UI_LABELS.riskScore}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center">
            {isLoading ? (
              <Skeleton className="h-20 w-20 rounded-full" />
            ) : (
              <RiskScoreGauge
                score={statistics?.averageRiskScore ?? 0}
                size="sm"
                showPercentage={false}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risk Distribution */}
        <Card>
          <CardHeader>
            <CardTitle>{UI_LABELS.riskDistribution}</CardTitle>
            <CardDescription>
              Verteilung der Entities nach Risikostufe
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-[200px] w-full" />
            ) : statistics ? (
              <RiskDistributionChart
                distribution={statistics.riskDistribution}
                totalEntities={statistics.totalEntities}
              />
            ) : null}
          </CardContent>
        </Card>

        {/* Top Risk Factors */}
        <Card>
          <CardHeader>
            <CardTitle>Top Risikofaktoren</CardTitle>
            <CardDescription>
              Durchschnittlicher Beitrag pro Faktor
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-[200px] w-full" />
            ) : statistics?.topRiskFactors ? (
              <div className="space-y-4">
                {statistics.topRiskFactors.map((factor) => (
                  <div key={factor.name} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span>{RISK_FACTOR_LABELS[factor.name]}</span>
                      <span className="font-medium">
                        {factor.averageContribution.toFixed(1)} Punkte
                      </span>
                    </div>
                    <div className="h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-orange-500 rounded-full transition-all"
                        style={{
                          width: `${Math.min(100, factor.averageContribution * 4)}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {/* Trend Chart */}
      <RiskTrendChart
        data={statistics?.trend ?? []}
        isLoading={isLoading}
        showHighRiskCount
      />

      {/* High Risk Entities Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-destructive" />
                {UI_LABELS.highRiskEntities}
              </CardTitle>
              <CardDescription>
                {'Entities mit Risiko-Score >= 50'}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <HighRiskEntitiesTable
            entities={
              riskLevelFilter === 'all'
                ? highRiskEntities
                : (filteredEntitiesData?.entities ?? [])
            }
            isLoading={isLoading || isLoadingFiltered}
            onRecalculate={handleRecalculateEntity}
            isRecalculating={recalculatingEntity}
          />
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Summary Card Component
 */
interface SummaryCardProps {
  title: string;
  value: number | string;
  icon: React.ElementType;
  variant?: 'default' | 'destructive';
  isLoading?: boolean;
}

function SummaryCard({
  title,
  value,
  icon: Icon,
  variant = 'default',
  isLoading = false,
}: SummaryCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon
          className={cn(
            'h-5 w-5',
            variant === 'destructive' ? 'text-destructive' : 'text-muted-foreground'
          )}
        />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <p
            className={cn(
              'text-2xl font-bold',
              variant === 'destructive' && 'text-destructive'
            )}
          >
            {value}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
