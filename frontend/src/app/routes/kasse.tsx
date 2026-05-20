/**
 * Kasse Route Layout
 *
 * Layout für alle Kassenbuch-Routen.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';

export const Route = createFileRoute('/kasse')({
  component: KasseLayout,
});

function KasseLayout() {
  return <Outlet />;
}
