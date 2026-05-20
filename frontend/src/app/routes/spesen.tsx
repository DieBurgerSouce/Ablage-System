/**
 * Spesen Route Layout
 *
 * Layout für alle Spesenabrechnung-Routen.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';

export const Route = createFileRoute('/spesen')({
  component: SpesenLayout,
});

function SpesenLayout() {
  return <Outlet />;
}
