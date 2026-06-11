/**
 * Queue Statistics Cards
 *
 * Übersicht über Queue-Statistiken mit Prioritäts-Verteilung.
 */

import { Clock, AlertTriangle, Banknote, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { useQueueStats } from '../hooks/useSmartQueue';

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

export function QueueStatsCards() {
  const { data: stats, isLoading } = useQueueStats();

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
    );
  }

  if (!stats) return null;

  const totalToday = stats.total_completed_today + stats.total_failed_today;
  const successRate = totalToday > 0
    ? (stats.total_completed_today / totalToday) * 100
    : 100;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {/* Warteschlange */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">In Warteschlange</CardTitle>
          <Clock className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.total_waiting}</div>
          <div className="flex items-center gap-2 mt-2">
            <Badge variant="secondary" className="text-xs">
              {stats.total_processing} in Bearbeitung
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Ø Wartezeit: {formatDuration(stats.avg_wait_time_seconds)}
          </p>
        </CardContent>
      </Card>

      {/* Skonto-Gefährdet */}
      <Card className={stats.skonto_at_risk > 0 ? 'border-amber-500' : ''}>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Skonto-Gefährdet</CardTitle>
          <Banknote className={`h-4 w-4 ${stats.skonto_at_risk > 0 ? 'text-amber-500' : 'text-muted-foreground'}`} />
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${stats.skonto_at_risk > 0 ? 'text-amber-500' : ''}`}>
            {stats.skonto_at_risk}
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Rechnungen mit Skonto-Frist nahe Ablauf
          </p>
          {stats.skonto_at_risk > 0 && (
            <Badge variant="outline" className="mt-2 text-amber-500 border-amber-500">
              Hohe Priorität
            </Badge>
          )}
        </CardContent>
      </Card>

      {/* Mahnungen */}
      <Card className={stats.dunning_pending > 0 ? 'border-red-500' : ''}>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Mahnungen</CardTitle>
          <AlertTriangle className={`h-4 w-4 ${stats.dunning_pending > 0 ? 'text-red-500' : 'text-muted-foreground'}`} />
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${stats.dunning_pending > 0 ? 'text-red-500' : ''}`}>
            {stats.dunning_pending}
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Erkannte Mahnungen warten auf Verarbeitung
          </p>
          {stats.dunning_pending > 0 && (
            <Badge variant="outline" className="mt-2 text-red-500 border-red-500">
              Dringend
            </Badge>
          )}
        </CardContent>
      </Card>

      {/* Erfolgsrate heute */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Erfolgsrate Heute</CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{successRate.toFixed(1)}%</div>
          <Progress value={successRate} className="mt-2" />
          <div className="flex items-center justify-between text-xs text-muted-foreground mt-2">
            <span className="text-green-500">{stats.total_completed_today} erfolgreich</span>
            <span className="text-red-500">{stats.total_failed_today} fehlgeschlagen</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
