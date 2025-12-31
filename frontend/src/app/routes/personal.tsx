/**
 * Personal Route Layout
 *
 * Layout für alle Personal-/HR-Routen.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';

export const Route = createFileRoute('/personal')({
  component: PersonalLayout,
});

function PersonalLayout() {
  return <Outlet />;
}
