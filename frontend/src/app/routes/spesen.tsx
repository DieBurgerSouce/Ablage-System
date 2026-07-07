/**
 * Spesen Route Layout
 *
 * Layout für alle Spesenabrechnung-Routen.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';

export const Route = createFileRoute('/spesen')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('finance'),
  component: SpesenLayout,
});

function SpesenLayout() {
  return <Outlet />;
}
