/**
 * Goals Page
 *
 * ESG-Ziele und deren Fortschritt.
 * Verbunden mit der ESG API via TanStack Query Hooks.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Plus, Target, TrendingUp, TrendingDown, Minus, AlertCircle } from 'lucide-react';
import { useGoals } from '../hooks/use-esg-queries';

export function GoalsPage() {
  const { data: goals, isLoading: goalsLoading, error: goalsError } = useGoals({ active_only: true });

  if (goalsError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden der Ziele: {goalsError.message}
        </AlertDescription>
      </Alert>
    );
  }

  // Calculate statistics from goals data
  const allGoals = goals ?? [];
  const onTrackGoals = allGoals.filter(g => g.on_track === true);
  const atRiskGoals = allGoals.filter(g => g.on_track === false && (g.progress_percentage ?? 0) >= 25);
  const offTrackGoals = allGoals.filter(g => g.on_track === false && (g.progress_percentage ?? 0) < 25);

  // Group goals by category
  const environmentalGoals = allGoals.filter(g => g.category === 'environmental');
  const socialGoals = allGoals.filter(g => g.category === 'social');
  const governanceGoals = allGoals.filter(g => g.category === 'governance');

  return (
    <div className="space-y-6">
      {/* Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">ESG-Ziele</h2>
          <p className="text-sm text-muted-foreground">
            Definieren und verfolgen Sie Ihre Nachhaltigkeitsziele
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" disabled title="Kommt bald" aria-label="Neues ESG-Ziel erstellen">
            <Plus className="h-4 w-4 mr-2" />
            Neues Ziel
          </Button>
        </div>
      </div>

      {/* Overview */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Gesamtziele</CardTitle>
          </CardHeader>
          <CardContent>
            {goalsLoading ? (
              <Skeleton className="h-8 w-12" />
            ) : (
              <div className="text-2xl font-bold">{allGoals.length}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-green-600" />
              Auf Kurs
            </CardTitle>
          </CardHeader>
          <CardContent>
            {goalsLoading ? (
              <Skeleton className="h-8 w-12" />
            ) : (
              <div className="text-2xl font-bold text-green-600">{onTrackGoals.length}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Minus className="h-4 w-4 text-amber-600" />
              Gefährdet
            </CardTitle>
          </CardHeader>
          <CardContent>
            {goalsLoading ? (
              <Skeleton className="h-8 w-12" />
            ) : (
              <div className="text-2xl font-bold text-amber-600">{atRiskGoals.length}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-red-600" />
              Verfehlt
            </CardTitle>
          </CardHeader>
          <CardContent>
            {goalsLoading ? (
              <Skeleton className="h-8 w-12" />
            ) : (
              <div className="text-2xl font-bold text-red-600">{offTrackGoals.length}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Goals by Category */}
      <div className="grid gap-6 md:grid-cols-3">
        {/* Environmental */}
        <GoalCategoryCard
          title="Umwelt (E)"
          color="green"
          goals={environmentalGoals}
          isLoading={goalsLoading}
        />

        {/* Social */}
        <GoalCategoryCard
          title="Soziales (S)"
          color="blue"
          goals={socialGoals}
          isLoading={goalsLoading}
        />

        {/* Governance */}
        <GoalCategoryCard
          title="Governance (G)"
          color="purple"
          goals={governanceGoals}
          isLoading={goalsLoading}
        />
      </div>

      {/* Goals Detail Table */}
      <Card>
        <CardHeader>
          <CardTitle>Alle Ziele</CardTitle>
          <CardDescription>
            Detailübersicht aller ESG-Ziele
          </CardDescription>
        </CardHeader>
        <CardContent>
          {goalsLoading ? (
            <div className="space-y-4">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : allGoals.length > 0 ? (
            <div className="space-y-4">
              {allGoals.map((goal) => (
                <div
                  key={goal.id}
                  className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <Target className={`h-5 w-5 ${getStatusColor(goal.on_track, goal.progress_percentage)}`} />
                    <div>
                      <p className="font-medium">{goal.title}</p>
                      <p className="text-sm text-muted-foreground">
                        {goal.target_year ? `Bis ${goal.target_year}` : 'Kein Zieldatum'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="w-32">
                      <Progress value={goal.progress_percentage ?? 0} className="h-2" />
                    </div>
                    <span className="text-sm font-medium w-12 text-right">
                      {goal.progress_percentage?.toFixed(0) ?? 0}%
                    </span>
                    <Badge className={getStatusBadgeClass(goal.on_track, goal.progress_percentage)}>
                      {getStatusLabel(goal.on_track, goal.progress_percentage)}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              Keine Ziele definiert
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface GoalCategoryCardProps {
  title: string;
  color: 'green' | 'blue' | 'purple';
  goals: Array<{
    id: string;
    title: string;
    progress_percentage?: number | null;
    on_track?: boolean | null;
  }>;
  isLoading: boolean;
}

function GoalCategoryCard({ title, color, goals, isLoading }: GoalCategoryCardProps) {
  const dotColors = {
    green: 'bg-green-500',
    blue: 'bg-blue-500',
    purple: 'bg-purple-500',
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <div className={`h-3 w-3 rounded-full ${dotColors[color]}`} />
          {title}
        </CardTitle>
        <CardDescription>{goals.length} Ziele</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          [...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))
        ) : goals.length > 0 ? (
          goals.slice(0, 4).map((goal) => (
            <div key={goal.id}>
              <div className="flex justify-between text-sm mb-1">
                <span className="truncate max-w-[150px]">{goal.title}</span>
                <span className={getProgressColor(goal.progress_percentage ?? undefined)}>
                  {goal.progress_percentage?.toFixed(0) ?? 0}%
                </span>
              </div>
              <Progress value={goal.progress_percentage ?? 0} className="h-2" />
            </div>
          ))
        ) : (
          <p className="text-sm text-muted-foreground text-center py-4">
            Keine Ziele in dieser Kategorie
          </p>
        )}
      </CardContent>
    </Card>
  );
}


function getProgressColor(progress?: number): string {
  if (progress === undefined || progress === null) return 'text-gray-600';
  if (progress >= 75) return 'text-green-600';
  if (progress >= 50) return 'text-amber-600';
  return 'text-red-600';
}

function getStatusColor(onTrack?: boolean, progress?: number): string {
  if (onTrack === true) return 'text-green-600';
  if ((progress ?? 0) >= 25) return 'text-amber-600';
  return 'text-red-600';
}

function getStatusLabel(onTrack?: boolean, progress?: number): string {
  if (onTrack === true) return 'Auf Kurs';
  if ((progress ?? 0) >= 25) return 'Gefährdet';
  return 'Verfehlt';
}

function getStatusBadgeClass(onTrack?: boolean, progress?: number): string {
  if (onTrack === true) return 'bg-green-600 hover:bg-green-700';
  if ((progress ?? 0) >= 25) return 'bg-amber-100 text-amber-800 hover:bg-amber-200';
  return 'bg-red-600 hover:bg-red-700';
}
