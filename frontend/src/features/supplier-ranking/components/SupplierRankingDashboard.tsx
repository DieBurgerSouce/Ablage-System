/**
 * Supplier Ranking Dashboard Component
 *
 * Hauptseite für das Lieferanten-Ranking System.
 */

import { useState } from 'react';
import {
  Award,
  RefreshCw,
  BarChart3,
  Users,
  TrendingUp,
  AlertTriangle,
  Filter,
  ArrowUpDown,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useSupplierRankingDashboard, useCompareSuppliersMutation } from '../hooks/use-supplier-ranking-queries';
import { SupplierRankingTable } from './SupplierRankingTable';
import { SupplierScoreCard } from './SupplierScoreCard';
import type { SupplierTier } from '../types/supplier-ranking-types';
import { TIER_COLORS, TIER_LABELS, UI_LABELS } from '../types/supplier-ranking-types';

interface SupplierRankingDashboardProps {
  className?: string;
}

export function SupplierRankingDashboard({ className }: SupplierRankingDashboardProps) {
  const [periodDays, setPeriodDays] = useState(365);
  const [selectedSuppliers, setSelectedSuppliers] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState('overview');

  const { report, tierDistribution, isLoading, isError, error, refetch } =
    useSupplierRankingDashboard(periodDays);
  const compareMutation = useCompareSuppliersMutation();

  const handleCompare = () => {
    if (selectedSuppliers.length >= 2) {
      compareMutation.mutate({ entityIds: selectedSuppliers, periodDays });
    }
  };

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
            <Award className="h-7 w-7" />
            {UI_LABELS.pageTitle}
          </h1>
          <p className="text-muted-foreground mt-1">
            Bewertung und Vergleich aller Lieferanten basierend auf 5 Kategorien.
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
          title="Lieferanten gesamt"
          value={isLoading ? undefined : report?.totalSuppliers}
          icon={Users}
          isLoading={isLoading}
        />
        <SummaryCard
          title="Durchschnittsscore"
          value={isLoading ? undefined : report?.avgOverallScore.toFixed(1)}
          suffix="/ 100"
          icon={BarChart3}
          isLoading={isLoading}
        />
        <SummaryCard
          title="Top-Lieferanten"
          value={
            isLoading
              ? undefined
              : (tierDistribution?.platinum || 0) + (tierDistribution?.gold || 0)
          }
          suffix="Platinum & Gold"
          icon={Award}
          isLoading={isLoading}
          valueClassName="text-amber-600 dark:text-amber-400"
        />
        <SummaryCard
          title="Kritische Lieferanten"
          value={isLoading ? undefined : tierDistribution?.critical || 0}
          icon={AlertTriangle}
          isLoading={isLoading}
          valueClassName="text-red-600 dark:text-red-400"
        />
      </div>

      {/* Tier Distribution */}
      {!isLoading && tierDistribution && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">{UI_LABELS.tierDistribution}</CardTitle>
            <CardDescription>Verteilung der Lieferanten nach Bewertungsstufe</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {(['platinum', 'gold', 'silver', 'bronze', 'critical'] as SupplierTier[]).map(
                (tier) => (
                  <TierDistributionItem
                    key={tier}
                    tier={tier}
                    count={tierDistribution[tier] || 0}
                    total={report?.totalSuppliers ?? 0}
                  />
                )
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Content Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="overview" className="gap-2">
              <BarChart3 className="h-4 w-4" />
              Übersicht
            </TabsTrigger>
            <TabsTrigger value="comparison" className="gap-2">
              <ArrowUpDown className="h-4 w-4" />
              Vergleich
            </TabsTrigger>
            <TabsTrigger value="top" className="gap-2">
              <TrendingUp className="h-4 w-4" />
              Top 10
            </TabsTrigger>
          </TabsList>

          {activeTab === 'comparison' && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">
                {selectedSuppliers.length} ausgewählt
              </span>
              <Button
                size="sm"
                onClick={handleCompare}
                disabled={selectedSuppliers.length < 2 || compareMutation.isPending}
              >
                {compareMutation.isPending ? (
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Filter className="h-4 w-4 mr-2" />
                )}
                Vergleichen
              </Button>
            </div>
          )}
        </div>

        <TabsContent value="overview" className="mt-4">
          {isLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : (
            <SupplierRankingTable
              suppliers={report?.topSuppliers || []}
              isLoading={isLoading}
            />
          )}
        </TabsContent>

        <TabsContent value="comparison" className="mt-4">
          {isLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : (
            <div className="space-y-6">
              <SupplierRankingTable
                suppliers={report?.topSuppliers || []}
                isLoading={isLoading}
                selectable
                selectedIds={selectedSuppliers}
                onSelectionChange={setSelectedSuppliers}
              />

              {compareMutation.isSuccess && compareMutation.data && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Vergleichsergebnis</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      {compareMutation.data.map((supplier) => (
                        <SupplierScoreCard
                          key={supplier.entityId}
                          ranking={supplier}
                          compact
                        />
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="top" className="mt-4">
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-48 w-full" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {report?.topSuppliers.slice(0, 4).map((supplier, index) => (
                <div key={supplier.entityId} className="relative">
                  <div className="absolute -top-2 -left-2 z-10">
                    <Badge
                      className={cn(
                        'text-lg font-bold px-3 py-1',
                        index === 0 && 'bg-amber-500 text-white',
                        index === 1 && 'bg-slate-400 text-white',
                        index === 2 && 'bg-orange-600 text-white',
                        index > 2 && 'bg-gray-500 text-white'
                      )}
                    >
                      #{index + 1}
                    </Badge>
                  </div>
                  <SupplierScoreCard ranking={supplier} />
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * Summary Card Component
 */
interface SummaryCardProps {
  title: string;
  value?: number | string;
  suffix?: string;
  icon: React.ElementType;
  isLoading?: boolean;
  valueClassName?: string;
}

function SummaryCard({
  title,
  value,
  suffix,
  icon: Icon,
  isLoading,
  valueClassName,
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
          </div>
          <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
            <Icon className="h-6 w-6 text-primary" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Tier Distribution Item
 */
interface TierDistributionItemProps {
  tier: SupplierTier;
  count: number;
  total: number;
}

function TierDistributionItem({ tier, count, total }: TierDistributionItemProps) {
  const tierColors = TIER_COLORS[tier];
  const percentage = total > 0 ? ((count / total) * 100).toFixed(1) : '0';

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-4 py-3 rounded-lg border',
        tierColors.bg,
        tierColors.border
      )}
    >
      <span className="text-2xl">{tierColors.icon}</span>
      <div>
        <p className={cn('font-medium', tierColors.text)}>{TIER_LABELS[tier]}</p>
        <p className="text-sm text-muted-foreground">
          {count} ({percentage}%)
        </p>
      </div>
    </div>
  );
}
