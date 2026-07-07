/**
 * Invoice Workflow Route
 *
 * Route für den vollautomatischen Rechnungsworkflow
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { InvoiceWorkflowPage } from '@/features/invoice-workflow';

export const Route = createFileRoute('/invoice-workflow')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('invoice_tracking'),
  component: InvoiceWorkflowPage,
});
