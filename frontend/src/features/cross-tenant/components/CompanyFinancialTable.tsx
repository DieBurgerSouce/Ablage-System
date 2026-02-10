/**
 * CompanyFinancialTable
 *
 * Tabelle mit Finanz-/Verarbeitungsstatistiken pro Firma.
 * Farblich markierte Zellen fuer Warteschlange und Fehler.
 */

import { useState, useMemo } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type {
  CompanyFinancialSummary,
  SortConfig,
  FinancialSortColumn,
} from '../types/cross-tenant-types';

// =============================================================================
// Formatierung
// =============================================================================

const numberFormatter = new Intl.NumberFormat('de-DE');

function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

// =============================================================================
// Sorting
// =============================================================================

function sortCompanies(
  companies: CompanyFinancialSummary[],
  sort: SortConfig<FinancialSortColumn>
): CompanyFinancialSummary[] {
  return [...companies].sort((a, b) => {
    const dir = sort.direction === 'asc' ? 1 : -1;

    switch (sort.column) {
      case 'company_name':
        return a.company_name.localeCompare(b.company_name, 'de-DE') * dir;
      case 'total_invoices':
        return (a.total_invoices - b.total_invoices) * dir;
      case 'processing_queued':
        return (a.processing_queued - b.processing_queued) * dir;
      case 'processing_completed':
        return (a.processing_completed - b.processing_completed) * dir;
      case 'processing_failed':
        return (a.processing_failed - b.processing_failed) * dir;
      default:
        return 0;
    }
  });
}

// =============================================================================
// Component
// =============================================================================

interface CompanyFinancialTableProps {
  companies: CompanyFinancialSummary[];
}

export function CompanyFinancialTable({ companies }: CompanyFinancialTableProps) {
  const [sort, setSort] = useState<SortConfig<FinancialSortColumn>>({
    column: 'company_name',
    direction: 'asc',
  });

  const sortedCompanies = useMemo(
    () => sortCompanies(companies, sort),
    [companies, sort]
  );

  function handleSort(column: FinancialSortColumn) {
    setSort((prev) => ({
      column,
      direction: prev.column === column && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  }

  function SortIcon({ column }: { column: FinancialSortColumn }) {
    if (sort.column !== column) {
      return <ArrowUpDown className="ml-1 inline h-3 w-3 text-muted-foreground/50" />;
    }
    return sort.direction === 'asc' ? (
      <ArrowUp className="ml-1 inline h-3 w-3" />
    ) : (
      <ArrowDown className="ml-1 inline h-3 w-3" />
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Finanz- und Verarbeitungsstatus</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead
                  className="cursor-pointer select-none"
                  onClick={() => handleSort('company_name')}
                >
                  Firma
                  <SortIcon column="company_name" />
                </TableHead>
                <TableHead className="w-[80px] text-center">Aktiv</TableHead>
                <TableHead
                  className="cursor-pointer select-none text-right"
                  onClick={() => handleSort('total_invoices')}
                >
                  Rechnungen
                  <SortIcon column="total_invoices" />
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none text-right"
                  onClick={() => handleSort('processing_queued')}
                >
                  In Warteschlange
                  <SortIcon column="processing_queued" />
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none text-right"
                  onClick={() => handleSort('processing_completed')}
                >
                  Verarbeitet
                  <SortIcon column="processing_completed" />
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none text-right"
                  onClick={() => handleSort('processing_failed')}
                >
                  Fehlgeschlagen
                  <SortIcon column="processing_failed" />
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedCompanies.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                    Keine Firmen gefunden.
                  </TableCell>
                </TableRow>
              ) : (
                sortedCompanies.map((company) => (
                  <TableRow
                    key={company.company_id}
                    className={cn(!company.is_active && 'opacity-60')}
                  >
                    <TableCell className="font-medium">
                      {company.company_name}
                    </TableCell>
                    <TableCell className="text-center">
                      <span
                        className={cn(
                          'inline-block h-2.5 w-2.5 rounded-full',
                          company.is_active ? 'bg-green-500' : 'bg-red-500'
                        )}
                        title={company.is_active ? 'Aktiv' : 'Inaktiv'}
                      />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatNumber(company.total_invoices)}
                    </TableCell>
                    <TableCell
                      className={cn(
                        'text-right tabular-nums',
                        company.processing_queued > 0 && 'text-yellow-600 dark:text-yellow-400 font-medium'
                      )}
                    >
                      {formatNumber(company.processing_queued)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-green-600 dark:text-green-400">
                      {formatNumber(company.processing_completed)}
                    </TableCell>
                    <TableCell
                      className={cn(
                        'text-right tabular-nums',
                        company.processing_failed > 0 && 'text-red-600 dark:text-red-400 font-medium'
                      )}
                    >
                      {formatNumber(company.processing_failed)}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
