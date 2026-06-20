// KPI Grid Component
// Responsive grid of KPI cards (2 cols mobile, 4 cols desktop)

import type { KPIData } from '../types/smart-dashboard-types';
import { KPICard } from './KPICard';
import { cn } from '@/lib/utils';

interface KPIGridProps {
  kpis: KPIData[];
  className?: string;
}

export function KPIGrid({ kpis, className }: KPIGridProps) {
  if (kpis.length === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        'grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4',
        className
      )}
    >
      {kpis.map((kpi) => (
        <KPICard key={kpi.key} kpi={kpi} />
      ))}
    </div>
  );
}
