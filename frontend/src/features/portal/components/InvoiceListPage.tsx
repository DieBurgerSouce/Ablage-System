/**
 * Invoice List Page
 *
 * Kundenportal Rechnungsliste mit Filter, Sortierung und Pagination.
 */

import { useState } from 'react';
import { Link } from '@tanstack/react-router';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  FileText,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
import { usePortalInvoices } from '../hooks/use-portal-queries';
import type { PortalInvoice, InvoiceStatus } from '../types';
import {
  INVOICE_STATUS_OPTIONS,
  INVOICE_STATUS_LABELS,
  INVOICE_STATUS_COLORS,
} from '../types';

const PAGE_SIZE = 20;

export function InvoiceListPage() {
  const [statusFilter, setStatusFilter] = useState<InvoiceStatus | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(0);

  const { data, isLoading, isError, error } = usePortalInvoices({
    status: statusFilter === 'all' ? undefined : statusFilter,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  // Client-side filtering by search query (invoice number)
  const filteredInvoices = data?.items.filter((invoice: PortalInvoice) =>
    invoice.invoice_number.toLowerCase().includes(searchQuery.toLowerCase())
  ) ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Rechnungen</h1>
        <p className="text-muted-foreground mt-1">
          Alle Ihre Rechnungen im Überblick
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Rechnungsnummer suchen..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            <Select
              value={statusFilter}
              onValueChange={(value) => {
                setStatusFilter(value as InvoiceStatus | 'all');
                setPage(0);
              }}
            >
              <SelectTrigger className="w-full sm:w-[200px]">
                <Filter className="mr-2 h-4 w-4" />
                <SelectValue placeholder="Status filtern" />
              </SelectTrigger>
              <SelectContent>
                {INVOICE_STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Rechnungsliste</CardTitle>
          <CardDescription>
            {data?.total ?? 0} Rechnungen gefunden
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : isError ? (
            <div className="text-center py-8 text-destructive">
              <p>Fehler beim Laden der Rechnungen</p>
              <p className="text-sm">{(error as Error)?.message}</p>
            </div>
          ) : filteredInvoices.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileText className="mx-auto h-12 w-12 opacity-50 mb-3" />
              <p>Keine Rechnungen gefunden.</p>
            </div>
          ) : (
            <>
              {/* Desktop Table */}
              <div className="hidden md:block overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Rechnungsnr.</TableHead>
                      <TableHead>Datum</TableHead>
                      <TableHead>Fällig</TableHead>
                      <TableHead className="text-right">Betrag</TableHead>
                      <TableHead className="text-right">Offen</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Aktionen</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredInvoices.map((invoice: PortalInvoice) => (
                      <TableRow key={invoice.id}>
                        <TableCell className="font-medium">
                          <Link
                            to="/portal/invoices/$id"
                            params={{ id: invoice.id }}
                            className="hover:underline text-primary"
                          >
                            {invoice.invoice_number}
                          </Link>
                        </TableCell>
                        <TableCell>{formatDate(invoice.invoice_date)}</TableCell>
                        <TableCell>{formatDate(invoice.due_date)}</TableCell>
                        <TableCell className="text-right">
                          {formatCurrency(invoice.amount)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatCurrency(invoice.outstanding_amount)}
                        </TableCell>
                        <TableCell>
                          <Badge className={INVOICE_STATUS_COLORS[invoice.status]} variant="secondary">
                            {INVOICE_STATUS_LABELS[invoice.status]}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="ghost" size="sm" asChild>
                            <Link to="/portal/invoices/$id" params={{ id: invoice.id }}>
                              Details
                            </Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Mobile Cards */}
              <div className="md:hidden space-y-3">
                {filteredInvoices.map((invoice: PortalInvoice) => (
                  <MobileInvoiceCard key={invoice.id} invoice={invoice} />
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-6">
                  <p className="text-sm text-muted-foreground">
                    Seite {page + 1} von {totalPages}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                      disabled={page === 0}
                    >
                      <ChevronLeft className="h-4 w-4" />
                      Zurück
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                      disabled={page >= totalPages - 1}
                    >
                      Weiter
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface MobileInvoiceCardProps {
  invoice: PortalInvoice;
}

function MobileInvoiceCard({ invoice }: MobileInvoiceCardProps) {
  return (
    <Link
      to="/portal/invoices/$id"
      params={{ id: invoice.id }}
      className="block p-4 rounded-lg border hover:bg-muted/50 transition-colors"
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <span className="font-medium">{invoice.invoice_number}</span>
          <Badge className={`ml-2 ${INVOICE_STATUS_COLORS[invoice.status]}`} variant="secondary">
            {INVOICE_STATUS_LABELS[invoice.status]}
          </Badge>
        </div>
        <div className="text-right">
          <div className="font-semibold">{formatCurrency(invoice.amount)}</div>
        </div>
      </div>
      <div className="flex justify-between text-sm text-muted-foreground">
        <span>Datum: {formatDate(invoice.invoice_date)}</span>
        <span>Fällig: {formatDate(invoice.due_date)}</span>
      </div>
      {invoice.outstanding_amount > 0 && invoice.outstanding_amount < invoice.amount && (
        <div className="mt-2 text-sm">
          <span className="text-muted-foreground">Offen: </span>
          <span className="font-medium">{formatCurrency(invoice.outstanding_amount)}</span>
        </div>
      )}
    </Link>
  );
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(amount);
}

function formatDate(dateString: string): string {
  return format(new Date(dateString), 'dd.MM.yyyy', { locale: de });
}

export default InvoiceListPage;
