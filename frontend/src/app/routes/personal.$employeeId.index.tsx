/**
 * Personal Employee Detail Index Route
 *
 * Mitarbeiter-Detailansicht.
 */

import { createFileRoute } from '@tanstack/react-router';
import { EmployeeDetailPage } from '@/features/personal';

export const Route = createFileRoute('/personal/$employeeId/')({
  component: EmployeeDetailPage,
});
