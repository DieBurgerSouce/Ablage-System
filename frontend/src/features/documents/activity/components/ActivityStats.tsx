/**
 * ActivityStats Component
 *
 * Statistik-Anzeige für Aktivitäten.
 */

import { useMemo } from 'react';
import { Activity, TrendingUp, Users, BarChart3 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import type { ActivityStatistics } from '../types';
import { ACTIVITY_TYPE_LABELS } from '../types';

interface ActivityStatsProps {
  stats: ActivityStatistics;
  className?: string;
}

// Farben für die Top-Typen
const TYPE_COLORS = [
  'bg-blue-500',
  'bg-green-500',
  'bg-yellow-500',
  'bg-purple-500',
  'bg-red-500',
];

export function ActivityStats({ stats, className }: ActivityStatsProps) {
  // Berechne Top 5 Activity-Typen
  const topTypes = useMemo(() => {
    const sorted = Object.entries(stats.activitiesByType)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5);

    const max = sorted[0]?.[1] || 1;

    return sorted.map(([type, count], index) => ({
      type,
      label: ACTIVITY_TYPE_LABELS[type] || type,
      count,
      percentage: Math.round((count / max) * 100),
      color: TYPE_COLORS[index] || 'bg-gray-500',
    }));
  }, [stats.activitiesByType]);

  // Durchschnitt pro Tag berechnen
  const avgPerDay = useMemo(() => {
    if (stats.activitiesByDay.length === 0) return 0;
    const total = stats.activitiesByDay.reduce((sum, day) => sum + day.count, 0);
    return Math.round(total / stats.activitiesByDay.length);
  }, [stats.activitiesByDay]);

  // Trend berechnen (letzte 7 Tage vs vorherige 7 Tage)
  const trend = useMemo(() => {
    const days = stats.activitiesByDay;
    if (days.length < 14) return 0;

    const recent = days.slice(-7).reduce((sum, d) => sum + d.count, 0);
    const previous = days.slice(-14, -7).reduce((sum, d) => sum + d.count, 0);

    if (previous === 0) return 100;
    return Math.round(((recent - previous) / previous) * 100);
  }, [stats.activitiesByDay]);

  return (
    <div className={cn('grid gap-4 md:grid-cols-2 lg:grid-cols-4', className)}>
      {/* Total Activities */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Gesamt</CardTitle>
          <Activity className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.totalActivities.toLocaleString('de-DE')}</div>
          <p className="text-xs text-muted-foreground">
            im ausgewählten Zeitraum
          </p>
        </CardContent>
      </Card>

      {/* Average per Day */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Pro Tag</CardTitle>
          <BarChart3 className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{avgPerDay}</div>
          <p className="text-xs text-muted-foreground">
            durchschnittliche Aktivitäten
          </p>
        </CardContent>
      </Card>

      {/* Trend */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Trend</CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className={cn(
            'text-2xl font-bold',
            trend > 0 && 'text-green-600',
            trend < 0 && 'text-red-600'
          )}>
            {trend > 0 ? '+' : ''}{trend}%
          </div>
          <p className="text-xs text-muted-foreground">
            gegenüber Vorwoche
          </p>
        </CardContent>
      </Card>

      {/* Active Users */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Aktive User</CardTitle>
          <Users className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.topUsers.length}</div>
          <p className="text-xs text-muted-foreground">
            in den Top 10
          </p>
        </CardContent>
      </Card>

      {/* Top Activity Types */}
      <Card className="md:col-span-2">
        <CardHeader>
          <CardTitle className="text-sm font-medium">Top Aktivitätstypen</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {topTypes.map(({ type, label, count, percentage, color }) => (
            <div key={type} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="truncate">{label}</span>
                <span className="text-muted-foreground">{count}</span>
              </div>
              <Progress value={percentage} className={cn('h-2', `[&>div]:${color}`)} />
            </div>
          ))}

          {topTypes.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">
              Keine Aktivitäten vorhanden
            </p>
          )}
        </CardContent>
      </Card>

      {/* Top Users */}
      {stats.topUsers.length > 0 && (
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm font-medium">Aktivste Benutzer</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {stats.topUsers.slice(0, 5).map((user, index) => (
                <div key={user.userId} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-muted-foreground w-5">
                      #{index + 1}
                    </span>
                    <span className="text-sm truncate">{user.userName}</span>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {user.activityCount} Aktivitäten
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
