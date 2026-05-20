/**
 * Holding Dashboard Route
 *
 * Multi-Company Holding-Sicht mit konsolidierten KPIs.
 */

import { createFileRoute } from '@tanstack/react-router';
import { HoldingDashboard } from '@/features/holding';

export const Route = createFileRoute('/holding')({
  component: HoldingPage,
});

function HoldingPage() {
  return (
    <div className="container py-6">
      <HoldingDashboard />
    </div>
  );
}
