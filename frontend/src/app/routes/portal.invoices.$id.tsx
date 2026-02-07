/**
 * Portal Invoice Detail Route
 *
 * Kundenportal Rechnungsdetailansicht.
 */

import { createFileRoute } from '@tanstack/react-router';
import { InvoiceDetailPage } from '@/features/portal';

export const Route = createFileRoute('/portal/invoices/$id')({
  component: InvoiceDetailPage,
});
