/**
 * Cross-Tenant Reports Admin Route
 *
 * Route für mandantenübergreifende Berichte.
 * Erfordert Superuser-Berechtigung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { CrossTenantDashboard } from '@/features/cross-tenant/components';

export const Route = createFileRoute('/admin/cross-tenant')({
  component: CrossTenantDashboard,
});
