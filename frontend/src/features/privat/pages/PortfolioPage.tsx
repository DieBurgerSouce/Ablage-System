/**
 * Portfolio Page
 *
 * Zeigt das Portfolio-Dashboard mit Vermoegensübersicht,
 * Asset-Allocation und finanziellen Zielen.
 */

import * as React from 'react';
import { PortfolioDashboard, FinancialHealthDashboard } from '../components';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  useSpaces,
  usePortfolioDashboard,
  useCreatePortfolioSnapshot,
} from '../hooks/use-privat-queries';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Wallet, HeartPulse, TrendingUp, Target, AlertCircle } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';

export function PortfolioPage() {
  // Hole Spaces um den ersten Space zu verwenden
  const { data: spaces = [], isLoading: spacesLoading } = useSpaces();
  const selectedSpaceId = spaces[0]?.id;

  // Portfolio Dashboard Daten
  const {
    data: portfolioData,
    isLoading: portfolioLoading,
    error: portfolioError,
    refetch: refetchPortfolio,
  } = usePortfolioDashboard(selectedSpaceId ?? '', {
    enabled: !!selectedSpaceId,
  });

  // Snapshot erstellen Mutation
  const createSnapshotMutation = useCreatePortfolioSnapshot();

  const handleRefresh = React.useCallback(async () => {
    if (selectedSpaceId) {
      await createSnapshotMutation.mutateAsync(selectedSpaceId);
      refetchPortfolio();
    }
  }, [selectedSpaceId, createSnapshotMutation, refetchPortfolio]);

  const isLoading = spacesLoading || portfolioLoading;

  // Kein Space vorhanden
  if (!spacesLoading && spaces.length === 0) {
    return (
      <div className="flex items-center justify-center h-96 p-8">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Wallet className="h-5 w-5" />
              Kein Space vorhanden
            </CardTitle>
            <CardDescription>
              Erstellen Sie zuerst einen Privat-Space, um das Portfolio zu nutzen.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  // Loading State
  if (isLoading) {
    return (
      <div className="space-y-6 p-8">
        <div>
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-4 w-96 mt-2" />
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  // Error State
  if (portfolioError) {
    return (
      <div className="p-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Fehler beim Laden</AlertTitle>
          <AlertDescription>
            Das Portfolio konnte nicht geladen werden. Bitte versuchen Sie es erneut.
            <Button
              variant="outline"
              size="sm"
              className="ml-4"
              onClick={() => refetchPortfolio()}
            >
              Erneut versuchen
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <Wallet className="h-8 w-8" />
          Portfolio-Übersicht
        </h1>
        <p className="text-muted-foreground mt-1">
          Vermögensüberblick, finanzielle Gesundheit und Ziele
        </p>
      </div>

      {/* Tabs for different views */}
      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 lg:w-[400px]">
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Übersicht
          </TabsTrigger>
          <TabsTrigger value="health" className="flex items-center gap-2">
            <HeartPulse className="h-4 w-4" />
            Gesundheit
          </TabsTrigger>
          <TabsTrigger value="goals" className="flex items-center gap-2">
            <Target className="h-4 w-4" />
            Ziele
          </TabsTrigger>
        </TabsList>

        {/* Portfolio Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          <PortfolioDashboard
            snapshot={portfolioData?.snapshot ?? null}
            historicalSnapshots={portfolioData?.historicalSnapshots ?? []}
            goals={portfolioData?.goals ?? []}
            isLoading={isLoading}
            onRefresh={handleRefresh}
          />
        </TabsContent>

        {/* Financial Health Tab */}
        <TabsContent value="health" className="space-y-6">
          <FinancialHealthDashboard spaceId={selectedSpaceId!} />
        </TabsContent>

        {/* Financial Goals Tab */}
        <TabsContent value="goals" className="space-y-6">
          <FinancialGoalsSection
            spaceId={selectedSpaceId!}
            goals={portfolioData?.goals ?? []}
            summary={portfolioData?.goalsSummary}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * Financial Goals Section
 * Dedicated view for managing financial goals
 */
interface FinancialGoalsSectionProps {
  spaceId: string;
  goals: Array<{
    id: string;
    name: string;
    goalType: string;
    targetValue: number;
    currentValue: number;
    targetDate: string;
    progressPercent: number;
    isOnTrack: boolean;
    status: string;
    priority: number;
  }>;
  summary?: {
    totalGoals: number;
    activeGoals: number;
    completedGoals: number;
    onTrackCount: number;
    totalTargetValue: number;
    totalCurrentValue: number;
  };
}

function FinancialGoalsSection({ goals, summary }: FinancialGoalsSectionProps) {
  const activeGoals = goals.filter((g) => g.status === 'active');
  const completedGoals = goals.filter((g) => g.status === 'completed');

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      {summary && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Aktive Ziele</CardDescription>
              <CardTitle className="text-2xl">{summary.activeGoals}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Auf Kurs</CardDescription>
              <CardTitle className="text-2xl text-green-600">{summary.onTrackCount}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Gesamtziel</CardDescription>
              <CardTitle className="text-2xl">
                {new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(
                  summary.totalTargetValue
                )}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Aktueller Wert</CardDescription>
              <CardTitle className="text-2xl">
                {new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(
                  summary.totalCurrentValue
                )}
              </CardTitle>
            </CardHeader>
          </Card>
        </div>
      )}

      {/* Active Goals */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5" />
            Aktive Ziele ({activeGoals.length})
          </CardTitle>
          <CardDescription>
            Ihre aktuellen finanziellen Ziele und deren Fortschritt
          </CardDescription>
        </CardHeader>
        <CardContent>
          {activeGoals.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">
              Keine aktiven Ziele vorhanden. Erstellen Sie ein neues Ziel, um Ihren
              finanziellen Fortschritt zu verfolgen.
            </p>
          ) : (
            <div className="space-y-4">
              {activeGoals.map((goal) => (
                <GoalCard key={goal.id} goal={goal} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Completed Goals */}
      {completedGoals.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-green-600">
              Erreichte Ziele ({completedGoals.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {completedGoals.map((goal) => (
                <div
                  key={goal.id}
                  className="flex items-center justify-between p-2 rounded-lg bg-green-50 dark:bg-green-950"
                >
                  <span className="font-medium">{goal.name}</span>
                  <span className="text-green-600">
                    {new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(
                      goal.targetValue
                    )}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/**
 * Individual Goal Card
 */
function GoalCard({
  goal,
}: {
  goal: {
    id: string;
    name: string;
    goalType: string;
    targetValue: number;
    currentValue: number;
    targetDate: string;
    progressPercent: number;
    isOnTrack: boolean;
    status: string;
    priority: number;
  };
}) {
  const progress = Math.min(goal.progressPercent, 100);
  const remaining = goal.targetValue - goal.currentValue;
  const targetDate = new Date(goal.targetDate);

  return (
    <div className="p-4 border rounded-lg">
      <div className="flex items-start justify-between mb-2">
        <div>
          <h4 className="font-semibold">{goal.name}</h4>
          <p className="text-sm text-muted-foreground">
            Ziel bis {targetDate.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' })}
          </p>
        </div>
        <div
          className={`px-2 py-1 rounded-full text-xs font-medium ${
            goal.isOnTrack
              ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
              : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300'
          }`}
        >
          {goal.isOnTrack ? 'Auf Kurs' : 'Aufholen noetig'}
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span>
            {new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(
              goal.currentValue
            )}
          </span>
          <span className="text-muted-foreground">
            {new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(
              goal.targetValue
            )}
          </span>
        </div>
        <div className="w-full bg-secondary rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all ${
              goal.isOnTrack ? 'bg-green-500' : 'bg-yellow-500'
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{progress.toFixed(1)}% erreicht</span>
          <span>
            Noch{' '}
            {new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(
              Math.max(remaining, 0)
            )}
          </span>
        </div>
      </div>
    </div>
  );
}

export default PortfolioPage;
