/**
 * InvoiceOverviewPage - Dashboard/Übersicht für Rechnungsverfolgung
 *
 * Zeigt:
 * - Stats Cards (KPIs)
 * - Status Chart
 * - Quick Actions
 * - Recent Invoices Preview
 */

import { useState, useCallback } from 'react';
import { useNavigate } from '@tanstack/react-router';
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
import { RefreshCw, TrendingUp, AlertTriangle } from 'lucide-react';
import type { InvoiceTrackingResponse, InvoiceFilter } from '../types/invoice-types';
import { UI_LABELS } from '../types/invoice-types';
import {
  useInvoicePage,
  useMarkInvoicePaid,
  useIncreaseDunning,
} from '../hooks/use-invoice-queries';
import { InvoiceStatsCards } from './InvoiceStatsCards';
import { InvoiceTable } from './InvoiceTable';
import { InvoiceDetailSheet } from './InvoiceDetailSheet';
import { InvoiceStatusChart } from './InvoiceStatusChart';

export function InvoiceOverviewPage() {
  const { toast } = useToast();
  const navigate = useNavigate();

  // State
  const [filter] = useState<Partial<InvoiceFilter>>({
    page: 1,
    perPage: 20,
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

  // Navigate to list with filter
  const navigateToListWithFilter = (filterOptions: { overdueOnly?: boolean; status?: string }) => {
    const searchParams = new URLSearchParams();
    if (filterOptions.overdueOnly) {
      searchParams.set('overdueOnly', 'true');
    }
    if (filterOptions.status) {
      searchParams.set('status', filterOptions.status);
    }
    navigate({
      to: '/admin/rechnungen/liste',
      search: searchParams.toString() ? Object.fromEntries(searchParams) : undefined,
    });
  };

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

      {/* Overview Content */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Status Chart */}
        <InvoiceStatusChart
          statistics={statistics}
          isLoading={isLoadingStatistics}
        />

        {/* Quick Actions Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              Schnellzugriff
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button
              variant="outline"
              className="w-full justify-start"
              onClick={() => navigateToListWithFilter({ overdueOnly: true })}
            >
              <AlertTriangle className="h-4 w-4 mr-2 text-red-500" />
              Überfällige Rechnungen anzeigen
              {statistics?.overdueInvoices.count ? (
                <span className="ml-auto text-muted-foreground">
                  ({statistics.overdueInvoices.count})
                </span>
              ) : null}
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start"
              onClick={() => navigateToListWithFilter({ status: 'dunning' })}
            >
              <TrendingUp className="h-4 w-4 mr-2 text-orange-500" />
              Rechnungen in Mahnung anzeigen
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Recent Invoices Preview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            Neueste Rechnungen
          </CardTitle>
        </CardHeader>
        <CardContent>
          <InvoiceTable
            invoices={invoices.slice(0, 5)}
            isLoading={isLoadingInvoices}
            onRowClick={handleRowClick}
            onMarkPaid={handleMarkPaid}
            onIncreaseDunning={handleIncreaseDunning}
          />
          {invoices.length > 5 && (
            <div className="mt-4 text-center">
              <Button
                variant="link"
                onClick={() => navigate({ to: '/admin/rechnungen/liste' })}
              >
                Alle {invoices.length} Rechnungen anzeigen
              </Button>
            </div>
          )}
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
