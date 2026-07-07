/**
 * Fraud Detection Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { FraudDashboard } from '@/features/fraud';

export const Route = createFileRoute('/fraud')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('risk_finanzki'),
  component: FraudPage,
});

function FraudPage() {
  return <FraudDashboard />;
}
