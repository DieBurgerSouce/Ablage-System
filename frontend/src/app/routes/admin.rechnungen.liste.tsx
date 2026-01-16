/**
 * admin.rechnungen.liste.tsx - Vollständige Rechnungsliste
 *
 * Route: /admin/rechnungen/liste
 * Zeigt die InvoiceListPage (vollständige Liste mit Filter und Pagination)
 * Unterstützt URL-Parameter: ?overdueOnly=true&status=dunning
 */

import { createFileRoute } from '@tanstack/react-router';
import { InvoiceListPage } from '@/features/invoices/components/InvoiceListPage';

export const Route = createFileRoute('/admin/rechnungen/liste')({
  component: RechnungenListePage,
});

function RechnungenListePage() {
  return <InvoiceListPage />;
}
