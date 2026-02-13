/**
 * Digital Twin Route
 *
 * Route for the Digital Twin Dashboard at /admin/digital-twin
 */

import { createFileRoute } from '@tanstack/react-router';
import { DigitalTwinDashboard } from '@/features/ceo-dashboard/components/DigitalTwinDashboard';

export const Route = createFileRoute('/admin/digital-twin')({
  component: DigitalTwinDashboard,
});
