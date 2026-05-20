/**
 * BPMN Process Engine Routes Layout
 *
 * Layout für alle BPMN-Prozess-Seiten.
 */

import { Outlet, createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/prozesse')({
  component: ProcessEngineLayout,
});

function ProcessEngineLayout() {
  return <Outlet />;
}
