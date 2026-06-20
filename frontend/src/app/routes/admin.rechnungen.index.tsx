/**
 * admin.rechnungen.index.tsx - Dashboard/Übersicht für Rechnungsverfolgung
 *
 * Standard-Route: /admin/rechnungen
 * Zeigt die InvoiceOverviewPage (Dashboard mit Stats, Chart, Quick Actions)
 */

import { createFileRoute } from '@tanstack/react-router';
import { lazyRoute } from '@/lib/lazyRoute';

const InvoiceOverviewPage = lazyRoute(() => import('@/features/invoices/components/InvoiceOverviewPage').then(m => ({ default: m.InvoiceOverviewPage })));

export const Route = createFileRoute('/admin/rechnungen/')({
  component: RechnungenIndexPage,
});

function RechnungenIndexPage() {
  return <InvoiceOverviewPage />;
}
