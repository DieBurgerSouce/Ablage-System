/**
 * Firmen Admin Route
 *
 * Multi-Mandanten-Verwaltung für Administratoren.
 */

import { createFileRoute } from '@tanstack/react-router';
import { CompanyAdminPage } from '@/features/admin/companies';

export const Route = createFileRoute('/admin/firmen')({
  component: CompanyAdminPage,
});
