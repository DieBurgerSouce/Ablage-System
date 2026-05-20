/**
 * Admin Approval SLA Route
 * Path: /admin/approval-sla
 */

import { createFileRoute } from '@tanstack/react-router';
import { SLADashboardPage } from '@/features/approval-enhanced';

export const Route = createFileRoute('/admin/approval-sla')({
  component: SLADashboardPage,
});
