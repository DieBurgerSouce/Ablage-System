/**
 * Portal Parent Layout Route
 *
 * Kundenportal mit separatem Layout und Authentifizierung.
 */

import { createFileRoute, Outlet, Navigate, useLocation } from '@tanstack/react-router';
import { PortalLayout } from '@/features/portal';
import { isPortalAuthenticated } from '@/features/portal';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';

export const Route = createFileRoute('/portal')({
  component: PortalLayoutWrapper,
});

function PortalLayoutWrapper() {
  // Check if authenticated - redirect to login if not
  const authenticated = isPortalAuthenticated();

  // Use TanStack Router hook instead of window.location for SSR compatibility
  const { pathname } = useLocation();

  // If not authenticated and not on login page, redirect
  if (!authenticated && !pathname.includes('/portal/login')) {
    return <Navigate to="/portal/login" />;
  }

  // If on login page, don't wrap with PortalLayout
  if (pathname.includes('/portal/login')) {
    return <Outlet />;
  }

  return (
    <PortalLayout>
      <UnifiedErrorBoundary context="general" variant="card">
        <Outlet />
      </UnifiedErrorBoundary>
    </PortalLayout>
  );
}
