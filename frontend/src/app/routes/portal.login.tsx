/**
 * Portal Login Route
 *
 * Kundenportal Login-Seite.
 */

import { createFileRoute, Navigate } from '@tanstack/react-router';
import { PortalLoginPage, isPortalAuthenticated } from '@/features/portal';

export const Route = createFileRoute('/portal/login')({
  component: PortalLoginRoute,
});

function PortalLoginRoute() {
  // If already authenticated, redirect to dashboard
  if (isPortalAuthenticated()) {
    return <Navigate to="/portal" />;
  }

  return <PortalLoginPage />;
}
