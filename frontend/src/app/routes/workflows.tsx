/**
 * Workflows Layout Route
 *
 * Container-Layout für alle Workflow-Seiten.
 */

import { createFileRoute, Outlet } from '@tanstack/react-router';

export const Route = createFileRoute('/workflows')({
  component: WorkflowsLayout,
});

function WorkflowsLayout() {
  return (
    <div className="p-8">
      <Outlet />
    </div>
  );
}
