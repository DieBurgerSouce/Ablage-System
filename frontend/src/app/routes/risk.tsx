/**
 * Risk Scoring Parent Route
 *
 * Layout-Wrapper für alle Risk Scoring Routen.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';

export const Route = createFileRoute('/risk')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('risk_finanzki'),
  component: () => <Outlet />,
});
