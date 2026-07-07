/**
 * Kasse Route Layout
 *
 * Layout für alle Kassenbuch-Routen.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';

export const Route = createFileRoute('/kasse')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('kasse'),
  component: KasseLayout,
});

function KasseLayout() {
  return <Outlet />;
}
