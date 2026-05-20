/**
 * Firmen Dashboard Route
 *
 * Multi-Firma Dashboard mit Metriken und Vergleichen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { CompanyDashboardPage } from '@/features/admin/companies';

export const Route = createFileRoute('/admin/firmen/dashboard')({
  component: CompanyDashboardPage,
});
