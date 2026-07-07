/**
 * German Finance Layout Route
 *
 * Container-Layout fuer Finanzbuchhaltung-Seiten (USt, BWA, Cashflow).
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';

export const Route = createFileRoute('/german-finance')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('accounting'),
  component: GermanFinanceLayout,
});

function GermanFinanceLayout() {
  return (
    <div className="p-8">
      <Outlet />
    </div>
  );
}
