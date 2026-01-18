/**
 * Firmen Admin Route
 *
 * Multi-Mandanten-Verwaltung fuer Administratoren.
 */

import { createFileRoute } from '@tanstack/react-router';
import { CompanyAdminPage } from '@/features/admin/companies';

export const Route = createFileRoute('/admin/firmen')({
  component: CompanyAdminPage,
});
