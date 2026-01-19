/**
 * Fraud Detection Stats Cards
 *
 * Zeigt Uebersichtskarten fuer Fraud-Statistiken.
 */

import { Card, CardContent } from '@/components/ui/card';
import {
  AlertTriangle,
  Shield,
  TrendingUp,
  TrendingDown,
  Minus,
  Euro,
} from 'lucide-react';
import type { FraudDashboardStats } from '../api/fraud-api';

interface FraudStatsCardsProps {
  stats: FraudDashboardStats;
}

export function FraudStatsCards({ stats }: FraudStatsCardsProps) {
  const formatCurrency = (value: number) =>
    new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);

  const TrendIcon = stats.trend === 'increasing'
    ? TrendingUp
    : stats.trend === 'decreasing'
    ? TrendingDown
    : Minus;

  const trendColor = stats.trend === 'increasing'
    ? 'text-red-600'
    : stats.trend === 'decreasing'
    ? 'text-green-600'
    : 'text-slate-600';

  const trendLabel = stats.trend === 'increasing'
    ? 'Steigend'
    : stats.trend === 'decreasing'
    ? 'Fallend'
    : 'Stabil';

  const cards = [
    {
      label: 'Alerts (30 Tage)',
      value: stats.total_alerts_30d.toString(),
      icon: AlertTriangle,
      color: stats.total_alerts_30d > 10 ? 'text-amber-600' : 'text-slate-600',
      bg: stats.total_alerts_30d > 10 ? 'bg-amber-50 dark:bg-amber-950' : 'bg-slate-50 dark:bg-slate-950',
    },
    {
      label: 'Kritische Alerts',
      value: stats.critical_alerts.toString(),
      icon: Shield,
      color: stats.critical_alerts > 0 ? 'text-red-600' : 'text-green-600',
      bg: stats.critical_alerts > 0 ? 'bg-red-50 dark:bg-red-950' : 'bg-green-50 dark:bg-green-950',
    },
    {
      label: 'Risiko-Summe',
      value: formatCurrency(stats.high_risk_amount),
      icon: Euro,
      color: stats.high_risk_amount > 50000 ? 'text-red-600' : 'text-slate-600',
      bg: stats.high_risk_amount > 50000 ? 'bg-red-50 dark:bg-red-950' : 'bg-slate-50 dark:bg-slate-950',
    },
    {
      label: 'Trend',
      value: trendLabel,
      icon: TrendIcon,
      color: trendColor,
      bg: stats.trend === 'increasing' ? 'bg-red-50 dark:bg-red-950' : 'bg-slate-50 dark:bg-slate-950',
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map((card, index) => {
        const Icon = card.icon;
        return (
          <Card key={index} className={card.bg}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">{card.label}</p>
                  <p className={`text-xl font-bold ${card.color}`}>{card.value}</p>
                </div>
                <Icon className={`h-5 w-5 ${card.color} opacity-70`} />
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
