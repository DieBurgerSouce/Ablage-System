/**
 * Tenant Limits Admin Route
 *
 * Route für das Tenant-Metriken Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { TenantMetricsDashboard } from '@/features/admin/tenant-limits';

export const Route = createFileRoute('/admin/tenant-limits')({
  component: TenantMetricsDashboard,
});
