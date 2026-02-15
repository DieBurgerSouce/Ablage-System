/**
 * German Finance Layout Route
 *
 * Container-Layout fuer Finanzbuchhaltung-Seiten (USt, BWA, Cashflow).
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';

export const Route = createFileRoute('/german-finance')({
  component: GermanFinanceLayout,
});

function GermanFinanceLayout() {
  return (
    <div className="p-8">
      <Outlet />
    </div>
  );
}
