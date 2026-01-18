/**
 * Berichte Route - Report Builder Dashboard
 *
 * Automatische Report-Generierung und Zeitplan-Verwaltung.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ReportsDashboard } from '@/features/reports';

export const Route = createFileRoute('/berichte')({
  component: ReportsDashboard,
});
