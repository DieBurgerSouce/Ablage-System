/**
 * ERP Stats Cards Component
 *
 * Zeigt Statistiken zu ERP-Integrationen.
 */

import {
  Database,
  CheckCircle,
  AlertTriangle,
  Activity,
} from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ERPStats } from '../types';

interface ERPStatsCardsProps {
  stats: ERPStats;
}

export function ERPStatsCards({ stats }: ERPStatsCardsProps) {
  const cards = [
    {
      title: 'Verbindungen gesamt',
      value: stats.total_connections,
      icon: Database,
      description: 'Konfigurierte ERP-Systeme',
    },
    {
      title: 'Aktive Verbindungen',
      value: stats.active_connections,
      icon: CheckCircle,
      description: 'Aktuell verbunden',
      valueClassName: 'text-green-600 dark:text-green-400',
    },
    {
      title: 'Offene Konflikte',
      value: stats.pending_conflicts,
      icon: AlertTriangle,
      description: 'Warten auf Auflösung',
      valueClassName: stats.pending_conflicts > 0
        ? 'text-yellow-600 dark:text-yellow-400'
        : undefined,
    },
    {
      title: 'Syncs (24h)',
      value: stats.syncs_last_24h,
      icon: Activity,
      description: 'Letzte 24 Stunden',
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
            <card.icon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${card.valueClassName || ''}`}>
              {card.value}
            </div>
            <p className="text-xs text-muted-foreground">{card.description}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
