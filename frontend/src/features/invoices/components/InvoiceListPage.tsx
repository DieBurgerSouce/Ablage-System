/**
 * InvoiceListPage - Vollständige Rechnungsliste
 *
 * Zeigt:
 * - Stats Cards (KPIs)
 * - Filter Bar
 * - Invoice Table
 * - Pagination
 * - Detail Sheet
 */

import { useState, useCallback } from 'react';
import { useSearch } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/components/ui/use-toast';
import { RefreshCw, AlertTriangle } from 'lucide-react';
import type { InvoiceTrackingResponse, InvoiceFilter, InvoiceStatus } from '../types/invoice-types';
import { UI_LABELS } from '../types/invoice-types';
import {
  useInvoicePage,
  useMarkInvoicePaid,
  useIncreaseDunning,
} from '../hooks/use-invoice-queries';
import { InvoiceStatsCards } from './InvoiceStatsCards';
import { InvoiceFilterBar } from './InvoiceFilterBar';
import { InvoiceTable } from './InvoiceTable';
import { InvoiceDetailSheet } from './InvoiceDetailSheet';
import { InvoicePagination } from './InvoicePagination';

export function InvoiceListPage() {
  const { toast } = useToast();

  // Read URL search params for initial filter
  let initialOverdueOnly: boolean | undefined;
  let initialStatus: InvoiceStatus | undefined;

  try {
    const search = useSearch({ strict: false }) as Record<string, string | undefined>;
    initialOverdueOnly = search?.overdueOnly === 'true' ? true : undefined;
    initialStatus = search?.status as InvoiceStatus | undefined;
  } catch {
    // Router context not available in tests
  }

  // State
  const [filter, setFilter] = useState<Partial<InvoiceFilter>>({
    page: 1,
    perPage: 20,
    overdueOnly: initialOverdueOnly,
    status: initialStatus,
  });
  const [selectedInvoice, setSelectedInvoice] = useState<InvoiceTrackingResponse | null>(null);
  const [detailSheetOpen, setDetailSheetOpen] = useState(false);
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<'markPaid' | 'increaseDunning' | null>(null);

  // Queries
  const {
    invoices,
    statistics,
    isLoadingInvoices,
    isLoadingStatistics,
    isFetching,
    isError,
    refetch,
  } = useInvoicePage(filter);

  // Mutations
  const markPaidMutation = useMarkInvoicePaid();
  const increaseDunningMutation = useIncreaseDunning();

  // Handlers
  const handleRowClick = useCallback((invoice: InvoiceTrackingResponse) => {
    setSelectedInvoice(invoice);
    setDetailSheetOpen(true);
  }, []);

  const handleMarkPaid = useCallback((invoice: InvoiceTrackingResponse) => {
    setSelectedInvoice(invoice);
    setConfirmAction('markPaid');
    setConfirmDialogOpen(true);
  }, []);

  const handleIncreaseDunning = useCallback((invoice: InvoiceTrackingResponse) => {
    setSelectedInvoice(invoice);
    setConfirmAction('increaseDunning');
    setConfirmDialogOpen(true);
  }, []);

  const confirmMarkPaid = async () => {
    if (!selectedInvoice) return;

    try {
      await markPaidMutation.mutateAsync({ invoiceId: selectedInvoice.id });
      toast({
        title: 'Erfolg',
        description: UI_LABELS.successMarkPaid,
      });
      setConfirmDialogOpen(false);
      setDetailSheetOpen(false);
    } catch {
      toast({
        variant: 'destructive',
        title: 'Fehler',
        description: UI_LABELS.errorMarkPaid,
      });
    }
  };

  const confirmIncreaseDunning = async () => {
    if (!selectedInvoice) return;

    try {
      await increaseDunningMutation.mutateAsync(selectedInvoice.id);
      toast({
        title: 'Erfolg',
        description: UI_LABELS.successIncreaseDunning,
      });
      setConfirmDialogOpen(false);
      setDetailSheetOpen(false);
    } catch {
      toast({
        variant: 'destructive',
        title: 'Fehler',
        description: UI_LABELS.errorIncreaseDunning,
      });
    }
  };

  const handleFilterChange = useCallback((newFilter: Partial<InvoiceFilter>) => {
    setFilter(newFilter);
  }, []);

  // Error state
  if (isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Fehler beim Laden
          </CardTitle>
          <CardDescription>
            Die Rechnungsdaten konnten nicht geladen werden. Bitte versuchen Sie es erneut.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={() => refetch()} variant="outline">
            <RefreshCw className="h-4 w-4 mr-2" />
            Erneut versuchen
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Actions Bar */}
      <div className="flex justify-end">
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
          Aktualisieren
        </Button>
      </div>

      {/* Stats Cards */}
      <InvoiceStatsCards
        statistics={statistics}
        isLoading={isLoadingStatistics}
      />

      {/* Filter Bar */}
      <InvoiceFilterBar
        filter={filter}
        onFilterChange={handleFilterChange}
      />

      {/* Full Table */}
      <Card>
        <CardContent className="pt-6">
          <InvoiceTable
            invoices={invoices}
            isLoading={isLoadingInvoices}
            onRowClick={handleRowClick}
            onMarkPaid={handleMarkPaid}
            onIncreaseDunning={handleIncreaseDunning}
          />

          {/* Pagination */}
          <InvoicePagination
            filter={filter}
            onFilterChange={handleFilterChange}
            totalItems={statistics?.totalInvoices ?? 0}
            isLoading={isLoadingInvoices}
          />
        </CardContent>
      </Card>

      {/* Detail Sheet */}
      <InvoiceDetailSheet
        invoice={selectedInvoice}
        open={detailSheetOpen}
        onOpenChange={setDetailSheetOpen}
        onMarkPaid={handleMarkPaid}
        onIncreaseDunning={handleIncreaseDunning}
        isLoading={markPaidMutation.isPending || increaseDunningMutation.isPending}
      />

      {/* Confirmation Dialog */}
      <AlertDialog open={confirmDialogOpen} onOpenChange={setConfirmDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmAction === 'markPaid'
                ? 'Als bezahlt markieren?'
                : 'Mahnstufe erhöhen?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmAction === 'markPaid' ? (
                <>
                  Möchten Sie die Rechnung{' '}
                  <span className="font-medium">
                    {selectedInvoice?.invoiceNumber ?? 'ohne Nummer'}
                  </span>{' '}
                  als bezahlt markieren?
                </>
              ) : (
                <>
                  Möchten Sie die Mahnstufe für Rechnung{' '}
                  <span className="font-medium">
                    {selectedInvoice?.invoiceNumber ?? 'ohne Nummer'}
                  </span>{' '}
                  von {selectedInvoice?.dunningLevel ?? 0} auf{' '}
                  {(selectedInvoice?.dunningLevel ?? 0) + 1} erhöhen?
                  {selectedInvoice?.dunningLevel === 3 && (
                    <span className="block mt-2 text-destructive font-medium">
                      Achtung: Mahnstufe 4 ist die letzte Mahnung vor Inkasso.
                    </span>
                  )}
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmAction === 'markPaid' ? confirmMarkPaid : confirmIncreaseDunning}
              className={
                confirmAction === 'increaseDunning'
                  ? 'bg-orange-600 hover:bg-orange-700'
                  : undefined
              }
              disabled={markPaidMutation.isPending || increaseDunningMutation.isPending}
            >
              {confirmAction === 'markPaid' ? (
                <>Als bezahlt markieren</>
              ) : (
                <>Mahnstufe erhöhen</>
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
