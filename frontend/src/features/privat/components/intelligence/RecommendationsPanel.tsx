/**
 * RecommendationsPanel - Smart Recommendations Anzeige
 *
 * Zeigt intelligente Empfehlungen basierend auf:
 * - Refinancing-Möglichkeiten
 * - Rebalancing-Bedarf
 * - Versicherungslücken
 * - Notfallfonds-Status
 * - Hohe Kosten-Alerts
 * - Fristen-Warnungen
 */

import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from '@tanstack/react-router';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Lightbulb, RefreshCw, TrendingDown, PieChart, Shield, Wallet, AlertTriangle, Calendar, Euro, Sparkles, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { privatIntelligenceService } from '@/lib/api/services/privat-intelligence';
import type { SmartRecommendation } from '@/types/privat';

interface RecommendationsPanelProps {
  spaceId: string;
  className?: string;
  maxItems?: number;
  showFilters?: boolean;
}

const PRIORITY_COLORS: Record<SmartRecommendation['priority'], string> = {
  kritisch: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
  hoch: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300',
  mittel: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300',
  niedrig: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
};

const PRIORITY_ORDER: Record<SmartRecommendation['priority'], number> = {
  kritisch: 0,
  hoch: 1,
  mittel: 2,
  niedrig: 3,
};

const CATEGORY_ICONS: Record<SmartRecommendation['category'], React.ReactNode> = {
  refinancing: <TrendingDown className="h-4 w-4" />,
  rebalancing: <PieChart className="h-4 w-4" />,
  insurance_gap: <Shield className="h-4 w-4" />,
  emergency_fund: <Wallet className="h-4 w-4" />,
  high_cost: <AlertTriangle className="h-4 w-4" />,
  deadline: <Calendar className="h-4 w-4" />,
  general: <Lightbulb className="h-4 w-4" />,
};

const CATEGORY_LABELS: Record<SmartRecommendation['category'], string> = {
  refinancing: 'Umschuldung',
  rebalancing: 'Rebalancing',
  insurance_gap: 'Versicherung',
  emergency_fund: 'Notfallfonds',
  high_cost: 'Hohe Kosten',
  deadline: 'Frist',
  general: 'Allgemein',
};

const CATEGORY_COLORS: Record<SmartRecommendation['category'], string> = {
  refinancing: 'text-green-600 dark:text-green-400',
  rebalancing: 'text-purple-600 dark:text-purple-400',
  insurance_gap: 'text-red-600 dark:text-red-400',
  emergency_fund: 'text-blue-600 dark:text-blue-400',
  high_cost: 'text-orange-600 dark:text-orange-400',
  deadline: 'text-amber-600 dark:text-amber-400',
  general: 'text-gray-600 dark:text-gray-400',
};

export function RecommendationsPanel({
  spaceId,
  className,
  maxItems = 10,
  showFilters = true,
}: RecommendationsPanelProps) {
  const [categoryFilter, setCategoryFilter] = React.useState<string | null>(null);
  const [priorityFilter, _setPriorityFilter] = React.useState<string | null>(null);

  const {
    data: recommendations,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['recommendations', spaceId, categoryFilter, priorityFilter],
    queryFn: () =>
      privatIntelligenceService.getRecommendations(spaceId, {
        category: categoryFilter || undefined,
        priority: priorityFilter || undefined,
        limit: maxItems,
      }),
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
            <Lightbulb className="h-5 w-5 text-red-500" />
            Empfehlungen
          </CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Empfehlungen
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className={cn('', className)}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-amber-500" />
              Smart Empfehlungen
            </CardTitle>
            <CardDescription>
              Personalisierte Vorschläge zur Optimierung
            </CardDescription>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Empfehlungen aktualisieren"
          >
            <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} aria-hidden="true" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LoadingSkeleton />
        ) : recommendations ? (
          <div className="space-y-4">
            {/* Summary Stats */}
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary" className="gap-1">
                <span className="font-bold">{recommendations.totalCount}</span>
                Empfehlungen
              </Badge>
              {recommendations.criticalCount > 0 && (
                <Badge variant="destructive" className="gap-1">
                  <span className="font-bold">{recommendations.criticalCount}</span>
                  kritisch
                </Badge>
              )}
              {recommendations.highCount > 0 && (
                <Badge className="bg-orange-500 gap-1">
                  <span className="font-bold">{recommendations.highCount}</span>
                  hoch
                </Badge>
              )}
              {recommendations.potentialTotalSavings > 0 && (
                <Badge variant="outline" className="gap-1 text-green-600 border-green-600">
                  <Euro className="h-3 w-3" />
                  {formatCurrency(recommendations.potentialTotalSavings)} Sparpotenzial
                </Badge>
              )}
            </div>

            {/* Filters */}
            {showFilters && (
              <div className="flex flex-wrap gap-2">
                <Button
                  variant={categoryFilter === null ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setCategoryFilter(null)}
                >
                  Alle
                </Button>
                {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
                  <Button
                    key={key}
                    variant={categoryFilter === key ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setCategoryFilter(categoryFilter === key ? null : key)}
                    className="gap-1"
                  >
                    {CATEGORY_ICONS[key as SmartRecommendation['category']]}
                    {label}
                  </Button>
                ))}
              </div>
            )}

            {/* Recommendations List */}
            <ScrollArea className="h-[400px] pr-4">
              <div className="space-y-3">
                {recommendations.recommendations
                  .sort((a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority])
                  .map((rec) => (
                    <RecommendationCard
                      key={rec.id}
                      recommendation={rec}
                      formatCurrency={formatCurrency}
                    />
                  ))}

                {recommendations.recommendations.length === 0 && (
                  <div className="text-center py-8 text-muted-foreground">
                    <Lightbulb className="h-12 w-12 mx-auto mb-3 opacity-50" />
                    <p>Keine Empfehlungen gefunden</p>
                    <p className="text-sm">
                      Ihre Finanzen sind gut aufgestellt!
                    </p>
                  </div>
                )}
              </div>
            </ScrollArea>

            {/* Last Updated */}
            <p className="text-xs text-muted-foreground text-right pt-2 border-t">
              Generiert am:{' '}
              {new Date(recommendations.generatedAt).toLocaleString('de-DE')}
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

interface RecommendationCardProps {
  recommendation: SmartRecommendation;
  formatCurrency: (amount: number) => string;
}

function RecommendationCard({ recommendation, formatCurrency }: RecommendationCardProps) {
  const CategoryIcon = CATEGORY_ICONS[recommendation.category];

  return (
    <div
      className={cn(
        'p-4 rounded-lg border transition-colors hover:bg-muted/50',
        recommendation.priority === 'kritisch' && 'border-red-300 dark:border-red-800',
        recommendation.priority === 'hoch' && 'border-orange-300 dark:border-orange-800'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1">
          <div
            className={cn(
              'p-2 rounded-lg bg-muted',
              CATEGORY_COLORS[recommendation.category]
            )}
          >
            {CategoryIcon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h4 className="font-medium text-sm truncate">{recommendation.title}</h4>
              <Badge className={cn('text-xs', PRIORITY_COLORS[recommendation.priority])}>
                {recommendation.priority}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground line-clamp-2">
              {recommendation.description}
            </p>

            {/* Savings/Gain */}
            <div className="flex flex-wrap gap-2 mt-2">
              {recommendation.potentialSavings && recommendation.potentialSavings > 0 && (
                <Badge variant="outline" className="text-green-600 border-green-600 text-xs">
                  Sparpotenzial: {formatCurrency(recommendation.potentialSavings)}
                </Badge>
              )}
              {recommendation.potentialGain && recommendation.potentialGain > 0 && (
                <Badge variant="outline" className="text-blue-600 border-blue-600 text-xs">
                  Gewinnpotenzial: {formatCurrency(recommendation.potentialGain)}
                </Badge>
              )}
              {recommendation.relatedEntityName && (
                <Badge variant="secondary" className="text-xs">
                  {recommendation.relatedEntityName}
                </Badge>
              )}
            </div>
          </div>
        </div>

        {/* Action */}
        {recommendation.actionUrl && (
          <Link to={recommendation.actionUrl}>
            <Button variant="ghost" size="sm" className="shrink-0">
              <ChevronRight className="h-4 w-4" />
            </Button>
          </Link>
        )}
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-6 w-24" />
        ))}
      </div>
      <div className="space-y-3">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    </div>
  );
}

export default RecommendationsPanel;
