/**
 * FieldDiffTable Component
 *
 * Tabellarische Darstellung der Feldunterschiede zwischen zwei Dokumenten.
 */

import { AlertTriangle, Plus, Minus, Edit2 } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { FieldChange, DifferenceType } from '../types';
import { FIELD_CATEGORY_LABELS, SIGNIFICANCE_LABELS } from '../types';

interface FieldDiffTableProps {
  fieldChanges: FieldChange[];
  showUnchanged?: boolean;
}

const diffTypeConfig: Record<
  DifferenceType,
  { icon: typeof Plus; label: string; className: string }
> = {
  added: {
    icon: Plus,
    label: 'Neu',
    className: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  },
  removed: {
    icon: Minus,
    label: 'Entfernt',
    className: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  },
  changed: {
    icon: Edit2,
    label: 'Geändert',
    className: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  },
  unchanged: {
    icon: Edit2,
    label: 'Gleich',
    className: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
  },
};

const significanceConfig: Record<string, { className: string }> = {
  critical: { className: 'bg-red-500 text-white' },
  high: { className: 'bg-orange-500 text-white' },
  medium: { className: 'bg-yellow-500 text-black' },
  low: { className: 'bg-gray-500 text-white' },
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '-';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

export function FieldDiffTable({ fieldChanges, showUnchanged = false }: FieldDiffTableProps) {
  const filteredChanges = showUnchanged
    ? fieldChanges
    : fieldChanges.filter((change) => change.changeType !== 'unchanged');

  if (filteredChanges.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p>Keine Feldunterschiede gefunden</p>
      </div>
    );
  }

  // Sortiere nach Signifikanz (kritisch zuerst)
  const sortedChanges = [...filteredChanges].sort((a, b) => {
    const order = { critical: 0, high: 1, medium: 2, low: 3 };
    return order[a.significance] - order[b.significance];
  });

  return (
    <div className="border rounded-lg overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/50">
            <TableHead className="w-[150px]">Feld</TableHead>
            <TableHead className="w-[100px]">Kategorie</TableHead>
            <TableHead className="w-[80px]">Typ</TableHead>
            <TableHead>Dokument 1</TableHead>
            <TableHead>Dokument 2</TableHead>
            <TableHead className="w-[100px]">Priorität</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedChanges.map((change, index) => {
            const config = diffTypeConfig[change.changeType];
            const Icon = config.icon;
            const isCritical = change.significance === 'critical';

            return (
              <TableRow
                key={`${change.fieldName}-${index}`}
                className={cn(isCritical && 'bg-red-50 dark:bg-red-900/10')}
              >
                <TableCell className="font-medium">
                  <div className="flex items-center gap-2">
                    {isCritical && (
                      <AlertTriangle className="h-4 w-4 text-red-500 flex-shrink-0" />
                    )}
                    <span className="truncate">{change.fieldName}</span>
                  </div>
                </TableCell>
                <TableCell>
                  <span className="text-xs text-muted-foreground">
                    {FIELD_CATEGORY_LABELS[change.category]}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary" className={cn('text-xs', config.className)}>
                    <Icon className="h-3 w-3 mr-1" />
                    {config.label}
                  </Badge>
                </TableCell>
                <TableCell>
                  <code
                    className={cn(
                      'text-xs px-2 py-1 rounded bg-muted font-mono block max-w-[200px] truncate',
                      change.changeType === 'removed' && 'bg-red-100 dark:bg-red-900/20',
                      change.changeType === 'changed' && 'bg-yellow-100 dark:bg-yellow-900/20'
                    )}
                    title={formatValue(change.oldValue)}
                  >
                    {formatValue(change.oldValue)}
                  </code>
                </TableCell>
                <TableCell>
                  <code
                    className={cn(
                      'text-xs px-2 py-1 rounded bg-muted font-mono block max-w-[200px] truncate',
                      change.changeType === 'added' && 'bg-green-100 dark:bg-green-900/20',
                      change.changeType === 'changed' && 'bg-green-100 dark:bg-green-900/20'
                    )}
                    title={formatValue(change.newValue)}
                  >
                    {formatValue(change.newValue)}
                  </code>
                </TableCell>
                <TableCell>
                  <Badge className={cn('text-xs', significanceConfig[change.significance]?.className)}>
                    {SIGNIFICANCE_LABELS[change.significance]}
                  </Badge>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
