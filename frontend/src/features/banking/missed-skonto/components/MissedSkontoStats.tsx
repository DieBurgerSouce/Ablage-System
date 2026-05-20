/**
 * Missed Skonto Stats
 * Statistik-Karten für verpasste Skonto-Übersicht
 */

import { TrendingDown, TrendingUp, Percent, AlertTriangle, CheckCircle, Clock } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatCurrency } from '@/features/banking/utils/format';
import type { SkontoStatistics } from '../types';

interface MissedSkontoStatsProps {
  statistics?: SkontoStatistics;
  isLoading?: boolean;
}

export function MissedSkontoStats({ statistics, isLoading }: MissedSkontoStatsProps) {
  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-8 w-32 mt-1" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-4 w-20" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!statistics) {
    return null;
  }

  const cards = [
    {
      title: 'Verpasste Ersparnis',
      value: formatCurrency(statistics.missedSavings),
      description: `${statistics.skontoMissedCount} Rechnungen`,
      icon: TrendingDown,
      iconColor: 'text-red-500',
      cardClass: 'border-red-200 bg-red-50/50',
    },
    {
      title: 'Genutzte Ersparnis',
      value: formatCurrency(statistics.totalSavings),
      description: `${statistics.skontoUsedCount} Rechnungen`,
      icon: CheckCircle,
      iconColor: 'text-green-500',
      cardClass: '',
    },
    {
      title: 'Offenes Potenzial',
      value: formatCurrency(statistics.potentialSavings),
      description: `${statistics.skontoPendingCount} Rechnungen`,
      icon: Clock,
      iconColor: 'text-blue-500',
      cardClass: '',
    },
    {
      title: 'Nutzungsrate',
      value: `${statistics.usageRate.toFixed(1)}%`,
      description: `${statistics.invoicesWithSkonto} mit Skonto`,
      icon: statistics.usageRate >= 70 ? TrendingUp : statistics.usageRate >= 50 ? Percent : AlertTriangle,
      iconColor:
        statistics.usageRate >= 70
          ? 'text-green-500'
          : statistics.usageRate >= 50
            ? 'text-yellow-500'
            : 'text-red-500',
      cardClass: '',
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title} className={card.cardClass}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
            <card.icon className={`h-4 w-4 ${card.iconColor}`} />
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
