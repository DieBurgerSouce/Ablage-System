/**
 * ValidationStats
 *
 * Statistik-Karten für das Validierungs-Dashboard.
 * Zeigt Übersichts-Metriken mit echten Daten.
 */

import { Clock, CheckCircle, AlertTriangle, FileText, Users, Activity } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import type { TrainingOverviewStats } from '../types';

interface ValidationStatsProps {
  stats?: TrainingOverviewStats;
  isLoading?: boolean;
}

export function ValidationStats({ stats, isLoading }: ValidationStatsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-card p-4 rounded-lg border shadow-sm">
            <div className="flex items-center gap-4">
              <Skeleton className="w-12 h-12 rounded-full" />
              <div className="space-y-2">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-6 w-12" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  const statItems = [
    {
      label: 'Ausstehend',
      value: stats?.pending_annotations ?? 0,
      icon: Clock,
      iconBg: 'bg-yellow-500/10',
      iconColor: 'text-yellow-600',
    },
    {
      label: 'Verifiziert',
      value: stats?.verified_samples ?? 0,
      icon: CheckCircle,
      iconBg: 'bg-green-500/10',
      iconColor: 'text-green-600',
    },
    {
      label: 'Korrekturen (24h)',
      value: stats?.recent_corrections_24h ?? 0,
      icon: AlertTriangle,
      iconBg: 'bg-orange-500/10',
      iconColor: 'text-orange-600',
    },
    {
      label: 'Gesamt Samples',
      value: stats?.total_samples ?? 0,
      icon: FileText,
      iconBg: 'bg-blue-500/10',
      iconColor: 'text-blue-600',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {statItems.map((item) => (
        <div
          key={item.label}
          className="bg-card p-4 rounded-lg border shadow-sm flex items-center gap-4"
        >
          <div className={`p-3 rounded-full ${item.iconBg}`}>
            <item.icon className={`w-6 h-6 ${item.iconColor}`} />
          </div>
          <div>
            <p className="text-sm text-muted-foreground">{item.label}</p>
            <h3 className="text-2xl font-bold">{item.value.toLocaleString('de-DE')}</h3>
          </div>
        </div>
      ))}
    </div>
  );
}
