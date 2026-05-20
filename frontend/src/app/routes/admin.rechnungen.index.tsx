/**
 * admin.rechnungen.index.tsx - Dashboard/Übersicht für Rechnungsverfolgung
 *
 * Standard-Route: /admin/rechnungen
 * Zeigt die InvoiceOverviewPage (Dashboard mit Stats, Chart, Quick Actions)
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const InvoiceOverviewPage = lazy(() => import('@/features/invoices/components/InvoiceOverviewPage').then(m => ({ default: m.InvoiceOverviewPage })));

export const Route = createFileRoute('/admin/rechnungen/')({
  component: RechnungenIndexPage,
});

function RechnungenIndexPage() {
  return (
    <Suspense fallback={<LazyLoadFallback />}>
      <InvoiceOverviewPage />
    </Suspense>
  );
}
