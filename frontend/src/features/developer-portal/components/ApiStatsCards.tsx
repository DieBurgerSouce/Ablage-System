/**
 * API Stats Cards
 *
 * Zeigt API-Nutzungsstatistiken im Developer Portal.
 */

import { Activity, Clock, AlertTriangle, Zap } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useApiStats } from '../hooks/useDeveloperPortal';

export function ApiStatsCards() {
  const { data: stats, isLoading } = useApiStats();

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-4" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-20" />
              <Skeleton className="h-3 w-32 mt-2" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!stats) return null;

  const cards = [
    {
      title: 'Anfragen heute',
      value: stats.total_requests_today.toLocaleString('de-DE'),
      description: `${stats.total_requests_month.toLocaleString('de-DE')} diesen Monat`,
      icon: Activity,
      color: 'text-blue-600',
    },
    {
      title: 'Ø Antwortzeit',
      value: `${stats.avg_response_time_ms} ms`,
      description: 'Durchschnittliche Latenz',
      icon: Clock,
      color: 'text-green-600',
    },
    {
      title: 'Fehlerrate',
      value: `${stats.error_rate_percent}%`,
      description: 'Letzte 24 Stunden',
      icon: AlertTriangle,
      color: stats.error_rate_percent > 5 ? 'text-red-600' : 'text-amber-600',
    },
    {
      title: 'Rate Limit',
      value: stats.rate_limit_remaining.toLocaleString('de-DE'),
      description: 'Verbleibende Anfragen',
      icon: Zap,
      color: stats.rate_limit_remaining < 100 ? 'text-red-600' : 'text-purple-600',
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
            <card.icon className={`h-4 w-4 ${card.color}`} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{card.value}</div>
            <p className="text-xs text-muted-foreground">{card.description}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
