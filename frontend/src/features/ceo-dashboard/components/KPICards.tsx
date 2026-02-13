/**
 * KPI Cards Component
 *
 * Displays key performance indicators in a grid layout.
 */

import { Card, CardContent } from '@/components/ui/card';
import type { OverviewData } from '../types';
import {
  FileText,
  Calendar,
  FileCheck,
  AlertTriangle,
  Bell,
  BellDot,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface KPICardsProps {
  overview: OverviewData;
}

interface KPICardProps {
  icon: React.ElementType;
  label: string;
  value: string | number;
  subtitle?: string;
  variant?: 'default' | 'warning' | 'success' | 'info';
}

function KPICard({ icon: Icon, label, value, subtitle, variant = 'default' }: KPICardProps) {
  const variantStyles = {
    default: 'text-foreground',
    warning: 'text-red-600 dark:text-red-400',
    success: 'text-green-600 dark:text-green-400',
    info: 'text-blue-600 dark:text-blue-400',
  };

  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-start gap-4">
          <div className={cn('rounded-lg p-3 bg-muted', variantStyles[variant])}>
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <div className="text-sm text-muted-foreground mb-1">{label}</div>
            <div className={cn('text-2xl font-bold', variantStyles[variant])}>
              {value}
            </div>
            {subtitle && (
              <div className="text-xs text-muted-foreground mt-1">{subtitle}</div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function KPICards({ overview }: KPICardsProps) {
  const { documents, invoices, alerts, autoProcessRate } = overview;

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatPercentage = (rate: number) => {
    return `${Math.round(rate * 100)}%`;
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {/* Documents Today */}
      <KPICard
        icon={FileText}
        label="Dokumente heute"
        value={documents.processedToday}
        variant="info"
      />

      {/* Documents This Month */}
      <KPICard
        icon={Calendar}
        label="Dokumente diesen Monat"
        value={documents.processedMonth}
        variant="default"
      />

      {/* Open Invoices */}
      <KPICard
        icon={FileCheck}
        label="Offene Rechnungen"
        value={invoices.openCount}
        subtitle={formatCurrency(invoices.openTotal)}
        variant="default"
      />

      {/* Overdue Invoices */}
      <KPICard
        icon={AlertTriangle}
        label="Überfällige Rechnungen"
        value={invoices.overdueCount}
        subtitle={formatCurrency(invoices.overdueTotal)}
        variant={invoices.overdueCount > 0 ? 'warning' : 'default'}
      />

      {/* Active Alerts */}
      <KPICard
        icon={Bell}
        label="Aktive Alerts"
        value={alerts.activeCount}
        variant="default"
      />

      {/* Critical Alerts */}
      <KPICard
        icon={BellDot}
        label="Kritische Alerts"
        value={alerts.criticalCount}
        variant={alerts.criticalCount > 0 ? 'warning' : 'default'}
      />

      {/* Auto-Processing Rate */}
      <KPICard
        icon={Zap}
        label="Auto-Verarbeitungsrate"
        value={formatPercentage(autoProcessRate)}
        variant="success"
      />
    </div>
  );
}
