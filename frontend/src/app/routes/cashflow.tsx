/**
 * Predictive Cash-Flow Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { CashflowDashboard } from '@/features/cashflow';

export const Route = createFileRoute('/cashflow')({
  component: CashflowPage,
});

function CashflowPage() {
  return <CashflowDashboard />;
}
