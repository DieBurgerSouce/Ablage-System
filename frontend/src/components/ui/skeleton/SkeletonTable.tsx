/**
 * SkeletonTable - Loading Skeleton für Tabellen
 *
 * Features:
 * - Konfigurierbare Zeilen- und Spaltenanzahl
 * - Optionale Header-Zeile
 * - Variierende Spaltenbreiten für natürliches Aussehen
 * - Animierte Pulse-Animation
 */

import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';

export interface SkeletonTableProps {
  /** Anzahl der Skeleton-Zeilen */
  rows?: number;
  /** Anzahl der Spalten */
  columns?: number;
  /** Header-Zeile anzeigen */
  showHeader?: boolean;
  /** Checkbox-Spalte anzeigen */
  showCheckbox?: boolean;
  /** Aktions-Spalte anzeigen */
  showActions?: boolean;
  /** Spaltenkonfiguration für Breiten */
  columnWidths?: ('sm' | 'md' | 'lg' | 'xl')[];
  /** Kompakte Darstellung */
  compact?: boolean;
  /** Zusätzliche CSS-Klassen */
  className?: string;
}

const WIDTH_CLASSES = {
  sm: 'w-16',
  md: 'w-24',
  lg: 'w-32',
  xl: 'w-48',
};

export function SkeletonTable({
  rows = 5,
  columns = 4,
  showHeader = true,
  showCheckbox = false,
  showActions = false,
  columnWidths,
  compact = false,
  className,
}: SkeletonTableProps) {
  // Generate column widths - either from prop or random
  const getColumnWidth = (index: number): string => {
    if (columnWidths && columnWidths[index]) {
      return WIDTH_CLASSES[columnWidths[index]];
    }
    // Pseudo-random but deterministic widths
    const widths = ['w-20', 'w-28', 'w-36', 'w-24', 'w-32', 'w-16'];
    return widths[index % widths.length];
  };

  const totalColumns = columns + (showCheckbox ? 1 : 0) + (showActions ? 1 : 0);

  return (
    <div className={cn('rounded-md border', className)}>
      <Table>
        {showHeader && (
          <TableHeader>
            <TableRow>
              {showCheckbox && (
                <TableHead className="w-[40px]">
                  <Skeleton className="h-4 w-4 rounded" />
                </TableHead>
              )}
              {Array.from({ length: columns }).map((_, i) => (
                <TableHead key={i}>
                  <Skeleton className={cn('h-4', getColumnWidth(i))} />
                </TableHead>
              ))}
              {showActions && (
                <TableHead className="w-[80px]">
                  <Skeleton className="h-4 w-12" />
                </TableHead>
              )}
            </TableRow>
          </TableHeader>
        )}
        <TableBody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <TableRow key={rowIndex}>
              {showCheckbox && (
                <TableCell className={compact ? 'py-2' : undefined}>
                  <Skeleton className="h-4 w-4 rounded" />
                </TableCell>
              )}
              {Array.from({ length: columns }).map((_, colIndex) => (
                <TableCell key={colIndex} className={compact ? 'py-2' : undefined}>
                  <Skeleton
                    className={cn(
                      'h-4',
                      getColumnWidth(colIndex),
                      // Vary heights slightly for first column (often avatar/icon)
                      colIndex === 0 && rowIndex % 3 === 0 && 'h-8 w-8 rounded-full'
                    )}
                  />
                </TableCell>
              ))}
              {showActions && (
                <TableCell className={compact ? 'py-2' : undefined}>
                  <div className="flex gap-1">
                    <Skeleton className="h-8 w-8 rounded" />
                    <Skeleton className="h-8 w-8 rounded" />
                  </div>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

SkeletonTable.displayName = 'SkeletonTable';

export default SkeletonTable;
