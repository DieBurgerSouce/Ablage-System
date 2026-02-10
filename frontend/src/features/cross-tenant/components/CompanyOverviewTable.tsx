/**
 * CompanyOverviewTable
 *
 * Tabelle mit Dokumenten-Statistiken pro Firma.
 * Sortierbar nach allen numerischen Spalten.
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type {
  CompanyOverviewStats,
  SortConfig,
  OverviewSortColumn,
  ActiveFilter,
} from '../types/cross-tenant-types';

// =============================================================================
// Formatierung
// =============================================================================

const numberFormatter = new Intl.NumberFormat('de-DE');

function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-';
  try {
    return new Intl.DateTimeFormat('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(dateStr));
  } catch {
    return '-';
  }
}

// =============================================================================
// Sorting
// =============================================================================

function sortCompanies(
  companies: CompanyOverviewStats[],
  sort: SortConfig<OverviewSortColumn>
): CompanyOverviewStats[] {
  return [...companies].sort((a, b) => {
    const dir = sort.direction === 'asc' ? 1 : -1;

    switch (sort.column) {
      case 'company_name':
        return a.company_name.localeCompare(b.company_name, 'de-DE') * dir;
      case 'total_documents':
        return (a.total_documents - b.total_documents) * dir;
      case 'documents_this_month':
        return (a.documents_this_month - b.documents_this_month) * dir;
      case 'archived_documents':
        return (a.archived_documents - b.archived_documents) * dir;
      case 'last_upload_date': {
        const dateA = a.last_upload_date ? new Date(a.last_upload_date).getTime() : 0;
        const dateB = b.last_upload_date ? new Date(b.last_upload_date).getTime() : 0;
        return (dateA - dateB) * dir;
      }
      default:
        return 0;
    }
  });
}

// =============================================================================
// Component
// =============================================================================

interface CompanyOverviewTableProps {
  companies: CompanyOverviewStats[];
}

export function CompanyOverviewTable({ companies }: CompanyOverviewTableProps) {
  const [sort, setSort] = useState<SortConfig<OverviewSortColumn>>({
    column: 'company_name',
    direction: 'asc',
  });
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('all');

  const filteredCompanies = useMemo(() => {
    if (activeFilter === 'all') return companies;
    return companies.filter((c) =>
      activeFilter === 'active' ? c.is_active : !c.is_active
    );
  }, [companies, activeFilter]);

  const sortedCompanies = useMemo(
    () => sortCompanies(filteredCompanies, sort),
    [filteredCompanies, sort]
  );

  function handleSort(column: OverviewSortColumn) {
    setSort((prev) => ({
      column,
      direction: prev.column === column && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  }

  function SortIcon({ column }: { column: OverviewSortColumn }) {
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
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-lg">Dokumenten-Uebersicht</CardTitle>
        <Select
          value={activeFilter}
          onValueChange={(v) => setActiveFilter(v as ActiveFilter)}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Firmen</SelectItem>
            <SelectItem value="active">Nur aktive</SelectItem>
            <SelectItem value="inactive">Nur inaktive</SelectItem>
          </SelectContent>
        </Select>
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
                  onClick={() => handleSort('total_documents')}
                >
                  Dokumente gesamt
                  <SortIcon column="total_documents" />
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none text-right"
                  onClick={() => handleSort('documents_this_month')}
                >
                  Diesen Monat
                  <SortIcon column="documents_this_month" />
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none text-right"
                  onClick={() => handleSort('archived_documents')}
                >
                  Archiviert
                  <SortIcon column="archived_documents" />
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none text-right"
                  onClick={() => handleSort('last_upload_date')}
                >
                  Letzter Upload
                  <SortIcon column="last_upload_date" />
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
                      {formatNumber(company.total_documents)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatNumber(company.documents_this_month)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatNumber(company.archived_documents)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatDate(company.last_upload_date)}
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
