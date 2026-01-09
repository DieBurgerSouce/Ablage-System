/**
 * FinancialHealthDashboard - Enterprise Financial Health Score Anzeige
 *
 * Zeigt den Financial Health Score mit 6 Dimensionen:
 * - Nettovermoegen-Trend
 * - Schulden-Management
 * - Versicherungs-Abdeckung
 * - Liquiditaet
 * - Altersvorsorge-Bereitschaft
 * - Diversifikation
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
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Activity,
  TrendingUp,
  Shield,
  Wallet,
  Clock,
  PieChart,
  AlertTriangle,
  CheckCircle2,
  Info,
  RefreshCw,
  Target,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { privatIntelligenceService } from '@/lib/api/services/privat-intelligence';
import type { FinancialHealthScore, HealthDimension } from '@/types/privat';

interface FinancialHealthDashboardProps {
  spaceId: string;
  className?: string;
  compact?: boolean;
}

const GRADE_COLORS: Record<FinancialHealthScore['grade'], string> = {
  A: 'text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-950',
  B: 'text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-950',
  C: 'text-yellow-600 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-950',
  D: 'text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-950',
  F: 'text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-950',
};

const GRADE_LABELS: Record<FinancialHealthScore['grade'], string> = {
  A: 'Ausgezeichnet',
  B: 'Gut',
  C: 'Befriedigend',
  D: 'Verbesserungswuerdig',
  F: 'Kritisch',
};

const DIMENSION_ICONS: Record<string, React.ReactNode> = {
  netWorthTrend: <TrendingUp className="h-4 w-4" />,
  debtManagement: <Wallet className="h-4 w-4" />,
  insuranceCoverage: <Shield className="h-4 w-4" />,
  liquidity: <Activity className="h-4 w-4" />,
  retirementReadiness: <Clock className="h-4 w-4" />,
  diversification: <PieChart className="h-4 w-4" />,
};

const DIMENSION_LABELS: Record<string, string> = {
  netWorthTrend: 'Vermoegensaufbau',
  debtManagement: 'Schulden-Management',
  insuranceCoverage: 'Versicherungsschutz',
  liquidity: 'Liquiditaet',
  retirementReadiness: 'Altersvorsorge',
  diversification: 'Diversifikation',
};

function getScoreColor(score: number): string {
  if (score >= 80) return 'text-green-600 dark:text-green-400';
  if (score >= 60) return 'text-blue-600 dark:text-blue-400';
  if (score >= 40) return 'text-yellow-600 dark:text-yellow-400';
  if (score >= 20) return 'text-orange-600 dark:text-orange-400';
  return 'text-red-600 dark:text-red-400';
}

function getProgressColor(score: number): string {
  if (score >= 80) return 'bg-green-500';
  if (score >= 60) return 'bg-blue-500';
  if (score >= 40) return 'bg-yellow-500';
  if (score >= 20) return 'bg-orange-500';
  return 'bg-red-500';
}

export function FinancialHealthDashboard({
  spaceId,
  className,
  compact = false,
}: FinancialHealthDashboardProps) {
  const {
    data: healthScore,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['financial-health', spaceId],
    queryFn: () => privatIntelligenceService.getFinancialHealthScore(spaceId),
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 1,
  });

  if (error) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-red-500" />
            Financial Health
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
        healthScore={healthScore}
        isLoading={isLoading}
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
              <Activity className="h-5 w-5 text-purple-500" />
              Financial Health Score
            </CardTitle>
            <CardDescription>
              Ihre finanzielle Gesundheit auf einen Blick
            </CardDescription>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Financial Health Score aktualisieren"
          >
            <RefreshCw className={cn('h-4 w-4', isFetching && 'animate-spin')} aria-hidden="true" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <LoadingSkeleton />
        ) : healthScore ? (
          <div className="space-y-6">
            {/* Overall Score */}
            <div
              className="flex items-center justify-center gap-8"
              role="region"
              aria-label="Financial Health Gesamtbewertung"
            >
              <div className="text-center">
                <div
                  className={cn(
                    'text-6xl font-bold',
                    getScoreColor(healthScore.overallScore)
                  )}
                  aria-label={`Gesamtscore: ${Math.round(healthScore.overallScore)} von 100 Punkten`}
                >
                  {Math.round(healthScore.overallScore)}
                </div>
                <p className="text-sm text-muted-foreground mt-1" aria-hidden="true">von 100</p>
              </div>
              <div className="text-center">
                <div
                  className={cn(
                    'text-5xl font-bold px-4 py-2 rounded-lg',
                    GRADE_COLORS[healthScore.grade]
                  )}
                  aria-label={`Bewertung: ${GRADE_LABELS[healthScore.grade]}`}
                >
                  {healthScore.grade}
                </div>
                <p className="text-sm text-muted-foreground mt-1" aria-hidden="true">
                  {GRADE_LABELS[healthScore.grade]}
                </p>
              </div>
            </div>

            {/* Dimensions */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {Object.entries(healthScore.dimensions).map(([key, dimension]) => (
                <DimensionCard
                  key={key}
                  dimensionKey={key}
                  dimension={dimension}
                />
              ))}
            </div>

            {/* Strengths & Weaknesses */}
            <div className="grid gap-4 md:grid-cols-2">
              {/* Strengths */}
              <div className="p-4 rounded-lg bg-green-50 dark:bg-green-950/30">
                <h4 className="font-medium text-green-700 dark:text-green-400 flex items-center gap-2 mb-3">
                  <CheckCircle2 className="h-4 w-4" />
                  Staerken
                </h4>
                <ul className="space-y-2">
                  {healthScore.topStrengths.map((strength, i) => (
                    <li
                      key={i}
                      className="text-sm text-green-600 dark:text-green-400 flex items-start gap-2"
                    >
                      <span className="mt-1">+</span>
                      {strength}
                    </li>
                  ))}
                  {healthScore.topStrengths.length === 0 && (
                    <li className="text-sm text-muted-foreground">
                      Keine besonderen Staerken identifiziert
                    </li>
                  )}
                </ul>
              </div>

              {/* Weaknesses */}
              <div className="p-4 rounded-lg bg-orange-50 dark:bg-orange-950/30">
                <h4 className="font-medium text-orange-700 dark:text-orange-400 flex items-center gap-2 mb-3">
                  <AlertTriangle className="h-4 w-4" />
                  Verbesserungspotenzial
                </h4>
                <ul className="space-y-2">
                  {healthScore.topWeaknesses.map((weakness, i) => (
                    <li
                      key={i}
                      className="text-sm text-orange-600 dark:text-orange-400 flex items-start gap-2"
                    >
                      <span className="mt-1">-</span>
                      {weakness}
                    </li>
                  ))}
                  {healthScore.topWeaknesses.length === 0 && (
                    <li className="text-sm text-muted-foreground">
                      Keine Schwaechen identifiziert
                    </li>
                  )}
                </ul>
              </div>
            </div>

            {/* Action Items */}
            {healthScore.actionItems.length > 0 && (
              <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-950/30">
                <h4 className="font-medium text-blue-700 dark:text-blue-400 flex items-center gap-2 mb-3">
                  <Target className="h-4 w-4" />
                  Empfohlene Massnahmen
                </h4>
                <ul className="space-y-2">
                  {healthScore.actionItems.map((item, i) => (
                    <li
                      key={i}
                      className="text-sm text-blue-600 dark:text-blue-400 flex items-start gap-2"
                    >
                      <span className="mt-1 font-bold">{i + 1}.</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Last Updated */}
            <p className="text-xs text-muted-foreground text-right">
              Zuletzt berechnet:{' '}
              {new Date(healthScore.calculatedAt).toLocaleString('de-DE')}
            </p>
          </div>
        ) : (
          <p className="text-center py-8 text-muted-foreground">
            Keine Daten verfuegbar
          </p>
        )}
      </CardContent>
    </Card>
  );
}

interface DimensionCardProps {
  dimensionKey: string;
  dimension: HealthDimension;
}

function DimensionCard({ dimensionKey, dimension }: DimensionCardProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="p-4 rounded-lg bg-muted/50 hover:bg-muted transition-colors cursor-help">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                {DIMENSION_ICONS[dimensionKey]}
                <span className="text-sm font-medium">
                  {DIMENSION_LABELS[dimensionKey]}
                </span>
              </div>
              <span className={cn('text-lg font-bold', getScoreColor(dimension.score))}>
                {Math.round(dimension.score)}
              </span>
            </div>
            <div className="relative h-2 bg-muted rounded-full overflow-hidden">
              <div
                className={cn('absolute h-full rounded-full transition-all', getProgressColor(dimension.score))}
                style={{ width: `${dimension.score}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground mt-2 line-clamp-1">
              {dimension.interpretation}
            </p>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <div className="space-y-2">
            <p className="font-medium">{DIMENSION_LABELS[dimensionKey]}</p>
            <p className="text-sm">{dimension.interpretation}</p>
            {dimension.recommendations.length > 0 && (
              <div className="pt-2 border-t">
                <p className="text-xs font-medium mb-1">Empfehlungen:</p>
                <ul className="text-xs space-y-1">
                  {dimension.recommendations.slice(0, 2).map((rec, i) => (
                    <li key={i}>- {rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

interface CompactViewProps {
  healthScore?: FinancialHealthScore;
  isLoading: boolean;
  className?: string;
}

function CompactView({ healthScore, isLoading, className }: CompactViewProps) {
  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="p-4">
          <div className="flex items-center gap-4">
            <Skeleton className="h-12 w-12 rounded-full" />
            <div className="flex-1">
              <Skeleton className="h-4 w-32 mb-2" />
              <Skeleton className="h-2 w-full" />
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!healthScore) {
    return null;
  }

  return (
    <Card className={className}>
      <CardContent className="p-4">
        <div className="flex items-center gap-4">
          <div
            className={cn(
              'h-12 w-12 rounded-full flex items-center justify-center text-xl font-bold',
              GRADE_COLORS[healthScore.grade]
            )}
          >
            {healthScore.grade}
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium">Financial Health</span>
              <span className={cn('font-bold', getScoreColor(healthScore.overallScore))}>
                {Math.round(healthScore.overallScore)}/100
              </span>
            </div>
            <div className="relative h-2 bg-muted rounded-full overflow-hidden">
              <div
                className={cn('absolute h-full rounded-full', getProgressColor(healthScore.overallScore))}
                style={{ width: `${healthScore.overallScore}%` }}
              />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-center gap-8">
        <Skeleton className="h-24 w-24 rounded-full" />
        <Skeleton className="h-20 w-16" />
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
    </div>
  );
}

export default FinancialHealthDashboard;
