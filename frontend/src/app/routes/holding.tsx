/**
 * Holding Dashboard Route
 *
 * Multi-Company Holding-Sicht mit konsolidierten KPIs.
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { HoldingDashboard } from '@/features/holding';

export const Route = createFileRoute('/holding')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('holding'),
  component: HoldingPage,
});

function HoldingPage() {
  return (
    <div className="container py-6">
      <HoldingDashboard />
    </div>
  );
}
