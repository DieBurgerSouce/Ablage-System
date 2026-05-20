/**
 * RecurringInvoiceList Component
 *
 * Tabellenansicht aller wiederkehrenden Rechnungen (Abos)
 * mit Filter, Pagination und Muster-Erkennung.
 */

import { useState, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  Search,
  RefreshCw,
  Sparkles,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
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
import { toast } from 'sonner';
import {
  useRecurringInvoices,
  useDetectPatterns,
} from '../hooks/useRecurringInvoices';
import {
  INTERVAL_LABELS,
  STATUS_LABELS,
  STATUS_VARIANTS,
} from '../types/recurring-types';
import type {
  RecurringInvoiceStatus,
  RecurringInvoiceResponse,
} from '../types/recurring-types';

// ==================== Helpers ====================

function formatEUR(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateStr));
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

// ==================== Component ====================

export default function RecurringInvoiceList() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<RecurringInvoiceStatus | 'all'>('all');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data, isLoading, isFetching } = useRecurringInvoices({
    status: statusFilter === 'all' ? undefined : statusFilter,
    page,
    page_size: pageSize,
  });

  const detectMutation = useDetectPatterns();

  const handleDetect = () => {
    detectMutation.mutate(undefined, {
      onSuccess: (patterns) => {
        toast.success(
          `${patterns.length} Muster erkannt`,
          { description: 'Abo-Muster wurden analysiert und gespeichert.' }
        );
      },
      onError: () => {
        toast.error('Fehler bei der Muster-Erkennung');
      },
    });
  };

  const handleRowClick = (invoice: RecurringInvoiceResponse) => {
    navigate({ to: '/recurring-invoices', search: { detail: invoice.id } });
  };

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;
  const invoiceItems = data?.items ?? [];

  const tableContainerRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: invoiceItems.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => 48,
    overscan: 5,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const totalVirtualSize = rowVirtualizer.getTotalSize();
  const paddingTop = virtualRows.length > 0 ? virtualRows[0]?.start ?? 0 : 0;
  const paddingBottom =
    virtualRows.length > 0
      ? totalVirtualSize - (virtualRows[virtualRows.length - 1]?.end ?? 0)
      : 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Abo-Rechnungen</CardTitle>
            <CardDescription>
              {data ? `${data.total} wiederkehrende Rechnungen` : 'Lade...'}
            </CardDescription>
          </div>
          <Button
            onClick={handleDetect}
            disabled={detectMutation.isPending}
            variant="outline"
          >
            {detectMutation.isPending ? (
              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 h-4 w-4" />
            )}
            Muster erkennen
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {/* Filter */}
        <div className="mb-4 flex items-center gap-4">
          <Select
            value={statusFilter}
            onValueChange={(val) => {
              setStatusFilter(val as RecurringInvoiceStatus | 'all');
              setPage(1);
            }}
          >
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Status filtern" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Status</SelectItem>
              <SelectItem value="active">Aktiv</SelectItem>
              <SelectItem value="paused">Pausiert</SelectItem>
              <SelectItem value="cancelled">Gekündigt</SelectItem>
              <SelectItem value="expired">Abgelaufen</SelectItem>
            </SelectContent>
          </Select>
          {isFetching && !isLoading && (
            <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" />
          )}
        </div>

        {/* Tabelle */}
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : invoiceItems.length > 0 ? (
          <>
            <div
              ref={tableContainerRef}
              className="overflow-auto max-h-[600px]"
            >
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-background shadow-sm">
                <TableRow>
                  <TableHead>Lieferant</TableHead>
                  <TableHead>Intervall</TableHead>
                  <TableHead className="text-right">Betrag</TableHead>
                  <TableHead>Nächste Fälligkeit</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Konfidenz</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paddingTop > 0 && (
                  <tr>
                    <td style={{ height: paddingTop }} colSpan={6} />
                  </tr>
                )}
                {virtualRows.map((virtualRow) => {
                  const invoice = invoiceItems[virtualRow.index];
                  return (
                  <TableRow
                    key={invoice.id}
                    data-index={virtualRow.index}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleRowClick(invoice)}
                    style={{ height: 48 }}
                  >
                    <TableCell className="font-medium">
                      {invoice.vendor_name}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {INTERVAL_LABELS[invoice.interval_type]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {formatEUR(invoice.expected_amount)}
                    </TableCell>
                    <TableCell>
                      {formatDate(invoice.next_expected_date)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANTS[invoice.status]}>
                        {STATUS_LABELS[invoice.status]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {formatPercent(invoice.detection_confidence)}
                    </TableCell>
                  </TableRow>
                  );
                })}
                {paddingBottom > 0 && (
                  <tr>
                    <td style={{ height: paddingBottom }} colSpan={6} />
                  </tr>
                )}
              </TableBody>
            </Table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-4 flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  Seite {page} von {totalPages}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Zurück
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                  >
                    Weiter
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="py-12 text-center text-muted-foreground">
            Keine Abo-Rechnungen gefunden.
            Nutzen Sie &quot;Muster erkennen&quot; um wiederkehrende Rechnungen automatisch zu finden.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
