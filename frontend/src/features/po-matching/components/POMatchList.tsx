/**
 * POMatchList - Tabellenansicht aller PO-Matches
 *
 * Zeigt eine paginierte Tabelle mit:
 * - Bestellnummer, Lieferant, Status, Dokumente, Score, Beträge, Datum
 * - Status-Badges mit Farbkodierung
 * - Auto-Matching Button
 * - Zeilen-Klick navigiert zur Detailansicht
 * - Paginierung
 */

import { useState, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Loader2, Zap, ChevronLeft, ChevronRight, FileSearch } from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePOMatches, useAutoMatch } from '../hooks/usePOMatching';
import type { MatchStatus, POMatchFilter } from '../types/po-matching-types';

// ==================== Helpers ====================

const STATUS_CONFIG: Record<
  MatchStatus,
  { label: string; className: string }
> = {
  pending: {
    label: 'Ausstehend',
    className: 'bg-gray-100 text-gray-800 border-gray-200',
  },
  partial: {
    label: 'Teilweise',
    className: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  },
  full: {
    label: 'Vollständig',
    className: 'bg-green-100 text-green-800 border-green-200',
  },
  discrepancy: {
    label: 'Abweichung',
    className: 'bg-red-100 text-red-800 border-red-200',
  },
  rejected: {
    label: 'Abgelehnt',
    className: 'bg-destructive text-destructive-foreground',
  },
  approved: {
    label: 'Freigegeben',
    className: 'bg-green-600 text-white border-green-700',
  },
};

function formatEUR(value: number | null): string {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(value);
}

function formatDate(isoDate: string | null): string {
  if (!isoDate) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(isoDate));
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return `${Math.round(value)}%`;
}

// ==================== Component ====================

export function POMatchList() {
  const navigate = useNavigate();
  const [page, setPage] = useState(0);
  const [pageSize] = useState(25);

  const filters: POMatchFilter = {
    page,
    page_size: pageSize,
  };

  const { data, isLoading, isFetching } = usePOMatches(filters);
  const autoMatch = useAutoMatch();

  const matches = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const tableContainerRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: matches.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => 48,
    overscan: 5,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0]?.start ?? 0 : 0;
  const paddingBottom =
    virtualRows.length > 0
      ? totalSize - (virtualRows[virtualRows.length - 1]?.end ?? 0)
      : 0;

  function handleRowClick(matchId: string) {
    navigate({
      to: '/po-matching',
      search: { tab: 'detail', matchId },
    });
  }

  function handleAutoMatch() {
    autoMatch.mutate();
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-xl font-semibold">
          PO-Matching Übersicht
        </CardTitle>
        <Button
          onClick={handleAutoMatch}
          disabled={autoMatch.isPending}
          size="sm"
        >
          {autoMatch.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Zap className="mr-2 h-4 w-4" />
          )}
          Auto-Matching ausführen
        </Button>
      </CardHeader>

      <CardContent>
        {/* Auto-Match Ergebnis */}
        {autoMatch.isSuccess && (
          <div className="mb-4 rounded-md bg-green-50 p-3 text-sm text-green-800 border border-green-200">
            Auto-Matching abgeschlossen: {autoMatch.data.matches_updated} Matches
            aktualisiert.
          </div>
        )}

        {/* Tabelle */}
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : matches.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <FileSearch className="h-12 w-12 mb-4" />
            <p className="text-lg font-medium">Keine Matches vorhanden</p>
            <p className="text-sm mt-1">
              Starten Sie das Auto-Matching, um Dokumente abzugleichen.
            </p>
          </div>
        ) : (
          <>
            <div
              ref={tableContainerRef}
              className="rounded-md border overflow-auto max-h-[600px]"
            >
              <Table>
                <TableHeader className="sticky top-0 z-10 bg-background shadow-sm">
                  <TableRow>
                    <TableHead>Bestellung</TableHead>
                    <TableHead>Lieferant</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-center">Dokumente</TableHead>
                    <TableHead className="text-right">Score</TableHead>
                    <TableHead className="text-right">Bestellung</TableHead>
                    <TableHead className="text-right">Lieferschein</TableHead>
                    <TableHead className="text-right">Rechnung</TableHead>
                    <TableHead>Datum</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paddingTop > 0 && (
                    <tr>
                      <td style={{ height: paddingTop }} colSpan={9} />
                    </tr>
                  )}
                  {virtualRows.map((virtualRow) => {
                    const match = matches[virtualRow.index];
                    const statusCfg = STATUS_CONFIG[match.match_status];

                    return (
                      <TableRow
                        key={match.id}
                        data-index={virtualRow.index}
                        className="cursor-pointer hover:bg-muted/50"
                        onClick={() => handleRowClick(match.id)}
                        style={{ height: 48 }}
                      >
                        <TableCell className="font-medium">
                          {match.order_number || '-'}
                        </TableCell>
                        <TableCell>
                          {match.vendor_name || '-'}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={cn('text-xs', statusCfg.className)}
                          >
                            {statusCfg.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-center">
                          <span className="tabular-nums">
                            {match.document_count}/3
                          </span>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatPercent(match.match_score)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatEUR(match.po_amount)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatEUR(match.dn_amount)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatEUR(match.invoice_amount)}
                        </TableCell>
                        <TableCell className="tabular-nums">
                          {formatDate(match.created_at)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {paddingBottom > 0 && (
                    <tr>
                      <td style={{ height: paddingBottom }} colSpan={9} />
                    </tr>
                  )}
                </TableBody>
              </Table>
            </div>

            {/* Paginierung */}
            <div className="flex items-center justify-between mt-4">
              <p className="text-sm text-muted-foreground">
                {total} Ergebnis{total !== 1 ? 'se' : ''} gesamt
                {isFetching && !isLoading && (
                  <Loader2 className="inline ml-2 h-3 w-3 animate-spin" />
                )}
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-sm tabular-nums">
                  Seite {page + 1} von {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setPage((p) => Math.min(totalPages - 1, p + 1))
                  }
                  disabled={page >= totalPages - 1}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
