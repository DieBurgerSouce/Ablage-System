/**
 * Portal Invoice List Route
 *
 * Kundenportal Rechnungsliste.
 */

import { createFileRoute } from '@tanstack/react-router';
import { InvoiceListPage } from '@/features/portal';

export const Route = createFileRoute('/portal/invoices')({
  component: InvoiceListPage,
});
