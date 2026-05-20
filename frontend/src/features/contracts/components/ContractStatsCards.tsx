/**
 * ContractStatsCards - KPI-Karten für Vertrags-Dashboard
 *
 * Zeigt:
 * - Gesamtzahl Verträge
 * - Aktive Verträge
 * - Bald ablaufend
 * - Kritische Fristen
 * - Gesamtwert
 * - Monatliche Verpflichtung
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  FileText,
  CheckCircle,
  AlertTriangle,
  Clock,
  Euro,
  TrendingUp,
} from 'lucide-react';
import type { ContractSummary } from '../types/contract-types';

interface ContractStatsCardsProps {
  summary?: ContractSummary;
  isLoading: boolean;
}

export function ContractStatsCards({ summary, isLoading }: ContractStatsCardsProps) {
  const stats = [
    {
      title: 'Gesamt',
      value: summary?.total_contracts ?? 0,
      icon: FileText,
      description: 'Verträge',
      color: 'text-blue-600',
      bgColor: 'bg-blue-100',
    },
    {
      title: 'Aktiv',
      value: summary?.active_contracts ?? 0,
      icon: CheckCircle,
      description: 'Laufende Verträge',
      color: 'text-green-600',
      bgColor: 'bg-green-100',
    },
    {
      title: 'Bald ablaufend',
      value: summary?.expiring_soon ?? 0,
      icon: Clock,
      description: 'In 90 Tagen',
      color: 'text-orange-600',
      bgColor: 'bg-orange-100',
    },
    {
      title: 'Kritische Fristen',
      value: summary?.critical_deadlines ?? 0,
      icon: AlertTriangle,
      description: 'Sofortige Aufmerksamkeit',
      color: 'text-red-600',
      bgColor: 'bg-red-100',
    },
    {
      title: 'Gesamtwert',
      value: summary?.total_value ?? 0,
      icon: Euro,
      description: 'Alle Verträge',
      color: 'text-purple-600',
      bgColor: 'bg-purple-100',
      isCurrency: true,
    },
    {
      title: 'Monatlich',
      value: summary?.monthly_commitment ?? 0,
      icon: TrendingUp,
      description: 'Verpflichtung',
      color: 'text-indigo-600',
      bgColor: 'bg-indigo-100',
      isCurrency: true,
    },
  ];

  const formatValue = (value: number, isCurrency: boolean) => {
    if (isCurrency) {
      return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }).format(value);
    }
    return value.toLocaleString('de-DE');
  };

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {stats.map((stat) => (
        <Card key={stat.title}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {stat.title}
            </CardTitle>
            <div className={`p-2 rounded-full ${stat.bgColor}`}>
              <stat.icon className={`h-4 w-4 ${stat.color}`} />
            </div>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {formatValue(stat.value, stat.isCurrency ?? false)}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {stat.description}
                </p>
              </>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
