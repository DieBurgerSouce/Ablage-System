/**
 * Risk Scoring Parent Route
 *
 * Layout-Wrapper fuer alle Risk Scoring Routen.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';

export const Route = createFileRoute('/risk')({
  component: () => <Outlet />,
});
