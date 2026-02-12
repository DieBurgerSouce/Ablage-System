/**
 * DashboardSkeleton - Loading-State für das Dashboard
 *
 * Nutzt SkeletonCardGrid mit variant="stats" für KPI-Karten
 * und SkeletonTable für die Dokumenten-Übersicht.
 */

import * as React from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { SkeletonCardGrid } from './SkeletonCard';
import { SkeletonTable } from './SkeletonTable';
import { cn } from '@/lib/utils';

export interface DashboardSkeletonProps {
  /** Anzahl der KPI-Karten */
  kpiCards?: number;
  /** Zeilen in der Tabellen-Vorschau */
  tableRows?: number;
  /** Zusätzliche CSS-Klassen */
  className?: string;
}

export const DashboardSkeleton = React.memo(function DashboardSkeleton({
  kpiCards = 4,
  tableRows = 5,
  className,
}: DashboardSkeletonProps) {
  return (
    <div className={cn('space-y-6', className)}>
      {/* Begrüßung */}
      <div className="space-y-1">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-48" />
      </div>

      {/* KPI-Karten */}
      <SkeletonCardGrid
        count={kpiCards}
        variant="stats"
        columns={4}
      />

      {/* Letzte Dokumente */}
      <div className="space-y-3">
        <Skeleton className="h-6 w-40" />
        <SkeletonTable
          rows={tableRows}
          columns={4}
          showCheckbox
          columnWidths={['xl', 'md', 'md', 'sm']}
        />
      </div>
    </div>
  );
});

DashboardSkeleton.displayName = 'DashboardSkeleton';

export default DashboardSkeleton;
