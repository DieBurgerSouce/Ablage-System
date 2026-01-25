/**
 * Admin Disaster Recovery Route
 *
 * Route für Disaster Recovery Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { DisasterRecoveryPage } from '@/features/admin/disaster-recovery';

export const Route = createFileRoute('/admin/disaster-recovery')({
  component: DisasterRecoveryPage,
});
