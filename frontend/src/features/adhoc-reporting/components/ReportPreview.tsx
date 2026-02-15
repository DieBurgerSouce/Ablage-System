/**
 * ReportPreview Component
 * German Enterprise Document Platform
 */

import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { ChevronLeft, ChevronRight, Database, FileSearch } from 'lucide-react';
import type { ExecutionResult } from '../types/adhoc-reporting-types';

interface ReportPreviewProps {
  result: ExecutionResult | null;
  isLoading: boolean;
  error?: Error | null;
  onPageChange?: (page: number) => void;
  currentPage?: number;
  pageSize?: number;
}

export function ReportPreview({
  result,
  isLoading,
  error,
  onPageChange,
  currentPage = 1,
  pageSize = 50,
}: ReportPreviewProps) {
  if (isLoading) {
    return (
      <Card className="p-6">
        <div className="space-y-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="p-8 text-center border-destructive/50">
        <Database className="h-12 w-12 mx-auto text-destructive mb-2" />
        <h3 className="font-semibold text-destructive mb-1">Fehler bei der Ausführung</h3>
        <p className="text-sm text-muted-foreground">{error.message}</p>
      </Card>
    );
  }

  if (!result) {
    return (
      <Card className="p-8 text-center">
        <FileSearch className="h-12 w-12 mx-auto text-muted-foreground mb-2" />
        <h3 className="font-semibold mb-1">Keine Vorschau verfügbar</h3>
        <p className="text-sm text-muted-foreground">
          Konfigurieren Sie Ihren Report, um eine Vorschau zu sehen
        </p>
      </Card>
    );
  }

  if (result.rows.length === 0) {
    return (
      <Card className="p-8 text-center">
        <FileSearch className="h-12 w-12 mx-auto text-muted-foreground mb-2" />
        <h3 className="font-semibold mb-1">Keine Ergebnisse</h3>
        <p className="text-sm text-muted-foreground">
          Ihre Abfrage hat keine Ergebnisse zurückgegeben
        </p>
      </Card>
    );
  }

  const totalPages = Math.ceil(result.total_rows / pageSize);
  const hasNextPage = currentPage < totalPages;
  const hasPrevPage = currentPage > 1;

  return (
    <Card>
      <div className="p-4 border-b flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Badge variant="secondary">
            {result.total_rows.toLocaleString('de-DE')} Zeilen
          </Badge>
          <span className="text-xs text-muted-foreground">
            Ausführungszeit: {result.execution_time_ms}ms
          </span>
        </div>
        {totalPages > 1 && onPageChange && (
          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(currentPage - 1)}
              disabled={!hasPrevPage}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm text-muted-foreground">
              Seite {currentPage} von {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(currentPage + 1)}
              disabled={!hasNextPage}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              {result.columns.map((column) => (
                <TableHead key={column} className="whitespace-nowrap">
                  {column}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {result.rows.map((row, rowIndex) => (
              <TableRow key={rowIndex}>
                {result.columns.map((column) => (
                  <TableCell key={column} className="whitespace-nowrap">
                    {formatCellValue(row[column])}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '-';
  }

  if (typeof value === 'boolean') {
    return value ? 'Ja' : 'Nein';
  }

  if (typeof value === 'number') {
    return value.toLocaleString('de-DE');
  }

  if (value instanceof Date) {
    return new Intl.DateTimeFormat('de-DE', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(value);
  }

  if (typeof value === 'string') {
    // Try to parse as date
    const dateMatch = value.match(/^\d{4}-\d{2}-\d{2}/);
    if (dateMatch) {
      const date = new Date(value);
      if (!isNaN(date.getTime())) {
        return new Intl.DateTimeFormat('de-DE', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
        }).format(date);
      }
    }
  }

  return String(value);
}
