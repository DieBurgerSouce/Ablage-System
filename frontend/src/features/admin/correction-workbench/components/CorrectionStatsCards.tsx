/**
 * Correction Stats Cards Component
 * Zeigt Statistiken zur Korrektur-Aktivitaet an
 */

import { Edit3, Clock, CheckCircle2, Users } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useCorrectionStats } from '../hooks';

export function CorrectionStatsCards() {
  const { data: stats, isLoading } = useCorrectionStats();

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-4" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
              <Skeleton className="h-3 w-32 mt-2" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Gesamt-Korrekturen</CardTitle>
          <Edit3 className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {stats?.totalCorrections.toLocaleString('de-DE') || 0}
          </div>
          <p className="text-xs text-muted-foreground">
            Alle eingereichten Korrekturen
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Heute</CardTitle>
          <Clock className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {stats?.correctionsToday.toLocaleString('de-DE') || 0}
          </div>
          <p className="text-xs text-muted-foreground">
            {stats?.correctionsThisWeek || 0} diese Woche
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Ausstehend</CardTitle>
          <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {stats?.pendingReview.toLocaleString('de-DE') || 0}
          </div>
          <p className="text-xs text-muted-foreground">
            Warten auf Pruefung
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Top-Beitragende</CardTitle>
          <Users className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {stats?.topContributors.length || 0}
          </div>
          <p className="text-xs text-muted-foreground">
            Aktive Korrektoren
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
