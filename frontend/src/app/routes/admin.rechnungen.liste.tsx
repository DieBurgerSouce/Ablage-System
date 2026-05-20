/**
 * admin.rechnungen.liste.tsx - Vollständige Rechnungsliste
 *
 * Route: /admin/rechnungen/liste
 * Zeigt die InvoiceListPage (vollständige Liste mit Filter und Pagination)
 * Unterstützt URL-Parameter: ?overdueOnly=true&status=dunning
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const InvoiceListPage = lazy(() => import('@/features/invoices/components/InvoiceListPage').then(m => ({ default: m.InvoiceListPage })));

export const Route = createFileRoute('/admin/rechnungen/liste')({
  component: RechnungenListePage,
});

function RechnungenListePage() {
  return (
    <Suspense fallback={<LazyLoadFallback />}>
      <InvoiceListPage />
    </Suspense>
  );
}
