/**
 * Predictive Cash-Flow Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { CashflowDashboard } from '@/features/cashflow';

export const Route = createFileRoute('/cashflow')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('finance'),
  component: CashflowPage,
});

function CashflowPage() {
  return <CashflowDashboard />;
}
