/**
 * Workflows Index Route
 *
 * Hauptseite mit Workflow-Liste und Statistiken.
 */

import { createFileRoute } from '@tanstack/react-router';
import { WorkflowsList, WorkflowStats } from '@/features/workflows';

export const Route = createFileRoute('/workflows/')({
  component: WorkflowsIndexPage,
});

function WorkflowsIndexPage() {
  return (
    <div className="space-y-8">
      {/* Statistiken */}
      <WorkflowStats />

      {/* Workflow-Liste */}
      <WorkflowsList />
    </div>
  );
}
