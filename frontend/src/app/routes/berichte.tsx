/**
 * Berichte Route - Report Builder Dashboard
 *
 * Haupt-Route mit Outlet für verschachtelte Routen (z.B. Builder).
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';

export const Route = createFileRoute('/berichte')({
  component: BerichteLayout,
});

function BerichteLayout() {
  return <Outlet />;
}
