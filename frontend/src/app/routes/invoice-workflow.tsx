/**
 * Invoice Workflow Route
 *
 * Route für den vollautomatischen Rechnungsworkflow
 */

import { createFileRoute } from '@tanstack/react-router';
import { InvoiceWorkflowPage } from '@/features/invoice-workflow';

export const Route = createFileRoute('/invoice-workflow')({
  component: InvoiceWorkflowPage,
});
