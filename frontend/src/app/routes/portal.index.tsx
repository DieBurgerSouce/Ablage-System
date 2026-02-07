/**
 * Portal Dashboard Route
 *
 * Kundenportal Startseite / Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { PortalDashboard } from '@/features/portal';

export const Route = createFileRoute('/portal/')({
  component: PortalDashboard,
});
