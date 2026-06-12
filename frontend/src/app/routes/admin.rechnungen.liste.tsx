/**
 * admin.rechnungen.liste.tsx - Vollständige Rechnungsliste
 *
 * Route: /admin/rechnungen/liste
 * Zeigt die InvoiceListPage (vollständige Liste mit Filter und Pagination)
 * Unterstützt URL-Parameter: ?overdueOnly=true&status=dunning&invoiceId=...
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const InvoiceListPage = lazy(() => import('@/features/invoices/components/InvoiceListPage').then(m => ({ default: m.InvoiceListPage })));

interface RechnungenListeSearch {
  overdueOnly?: string;
  status?: string;
  invoiceId?: string;
}

export const Route = createFileRoute('/admin/rechnungen/liste')({
  validateSearch: (search: Record<string, unknown>): RechnungenListeSearch => ({
    overdueOnly:
      typeof search.overdueOnly === 'string' ? search.overdueOnly : undefined,
    status: typeof search.status === 'string' ? search.status : undefined,
    invoiceId:
      typeof search.invoiceId === 'string' ? search.invoiceId : undefined,
  }),
  component: RechnungenListePage,
});

function RechnungenListePage() {
  return (
    <Suspense fallback={<LazyLoadFallback />}>
      <InvoiceListPage />
    </Suspense>
  );
}
