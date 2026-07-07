/**
 * Banking Missed Skonto Route
 * Route für verpasste Skonto-Übersicht
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { MissedSkontoDashboard } from '@/features/banking/missed-skonto';

export const Route = createFileRoute('/banking/missed-skonto')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('banking'),
  component: MissedSkontoPage,
});

function MissedSkontoPage() {
  return <MissedSkontoDashboard />;
}
