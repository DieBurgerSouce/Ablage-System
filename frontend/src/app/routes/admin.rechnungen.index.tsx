/**
 * admin.rechnungen.index.tsx - Dashboard/Übersicht für Rechnungsverfolgung
 *
 * Standard-Route: /admin/rechnungen
 * Zeigt die InvoiceOverviewPage (Dashboard mit Stats, Chart, Quick Actions)
 */

import { createFileRoute } from '@tanstack/react-router';
import { InvoiceOverviewPage } from '@/features/invoices/components/InvoiceOverviewPage';

export const Route = createFileRoute('/admin/rechnungen/')({
  component: RechnungenIndexPage,
});

function RechnungenIndexPage() {
  return <InvoiceOverviewPage />;
}
