/**
 * Banking Auto-Mahnlauf Route
 * Route für automatischen Mahnlauf Dashboard
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { AutoMahnlaufDashboard } from '@/features/banking/components';

export const Route = createFileRoute('/banking/auto-mahnlauf')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('banking'),
  component: AutoMahnlaufPage,
});

function AutoMahnlaufPage() {
  return <AutoMahnlaufDashboard />;
}
