/**
 * MLOps Statistics Cards
 *
 * Zeigt Uebersicht ueber Model Registry und Retraining Status.
 */

import { Brain, RefreshCw, CheckCircle, AlertTriangle, TrendingUp } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useMLOpsStats } from '../hooks/useMLOps';

export function MLOpsStatsCards() {
  const { data: stats, isLoading } = useMLOpsStats();

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="p-6">
              <Skeleton className="h-8 w-20 mb-2" />
              <Skeleton className="h-4 w-28" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const cards = [
    {
      title: 'Registrierte Modelle',
      value: stats?.total_models ?? 0,
      icon: Brain,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
    },
    {
      title: 'Aktive Modelle',
      value: stats?.active_models ?? 0,
      icon: CheckCircle,
      color: 'text-green-500',
      bgColor: 'bg-green-500/10',
    },
    {
      title: 'Ausstehende Retrainings',
      value: stats?.pending_retraining ?? 0,
      icon: RefreshCw,
      color: stats?.pending_retraining ? 'text-yellow-500' : 'text-muted-foreground',
      bgColor: stats?.pending_retraining ? 'bg-yellow-500/10' : 'bg-muted/50',
    },
    {
      title: 'Retraining Jobs (gesamt)',
      value: stats?.total_retraining_jobs ?? 0,
      icon: RefreshCw,
      color: 'text-purple-500',
      bgColor: 'bg-purple-500/10',
    },
    {
      title: 'Durchschn. Accuracy',
      value: stats?.average_accuracy
        ? `${(stats.average_accuracy * 100).toFixed(1)}%`
        : '-',
      icon: TrendingUp,
      color: 'text-emerald-500',
      bgColor: 'bg-emerald-500/10',
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <Card key={card.title}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-2xl font-bold">{card.value}</p>
                  <p className="text-sm text-muted-foreground">{card.title}</p>
                </div>
                <div className={`p-3 rounded-lg ${card.bgColor}`}>
                  <Icon className={`h-5 w-5 ${card.color}`} />
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
