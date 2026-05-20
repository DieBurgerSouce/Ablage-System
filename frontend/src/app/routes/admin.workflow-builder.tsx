import { createFileRoute } from '@tanstack/react-router';
import { WorkflowBuilder } from '@/features/workflow-builder';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';

export const Route = createFileRoute('/admin/workflow-builder')({
  component: WorkflowBuilderRoute,
});

function WorkflowBuilderRoute() {
  return (
    <UnifiedErrorBoundary context="general" variant="card">
      <WorkflowBuilder />
    </UnifiedErrorBoundary>
  );
}
