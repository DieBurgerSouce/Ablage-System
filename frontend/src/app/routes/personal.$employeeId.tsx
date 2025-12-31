/**
 * Personal Employee Detail Route Layout
 *
 * Layout fuer einzelne Mitarbeiter-Detailseiten.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';

export const Route = createFileRoute('/personal/$employeeId')({
  component: EmployeeDetailLayout,
});

function EmployeeDetailLayout() {
  return <Outlet />;
}
