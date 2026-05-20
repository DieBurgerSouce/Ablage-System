/**
 * Privat Route Layout
 *
 * Layout für alle Privat-Modul-Routen.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';

export const Route = createFileRoute('/privat')({
  component: PrivatLayout,
});

function PrivatLayout() {
  return <Outlet />;
}
