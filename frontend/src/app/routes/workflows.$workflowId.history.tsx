/**
 * Workflow Execution History Route
 *
 * Zeigt die Ausführungshistorie eines Workflows.
 */

import { createFileRoute } from '@tanstack/react-router';
import { WorkflowExecutionHistory, useWorkflow } from '@/features/workflows';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { AlertCircle, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Link } from '@tanstack/react-router';

export const Route = createFileRoute('/workflows/$workflowId/history')({
  component: WorkflowHistoryPage,
});

function WorkflowHistoryPage() {
  const { workflowId } = Route.useParams();
  const { data: workflow, isLoading, error } = useWorkflow(workflowId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (error || !workflow) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Fehler</AlertTitle>
        <AlertDescription>
          Der Workflow konnte nicht geladen werden.
          <Button variant="link" asChild className="ml-2">
            <Link to="/workflows">Zurück zur Übersicht</Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" asChild>
          <Link to="/workflows/$workflowId" params={{ workflowId }}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Zurück zum Workflow
          </Link>
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-bold">Ausführungshistorie</h1>
        <p className="text-muted-foreground">
          {workflow.name} - Alle bisherigen Ausführungen
        </p>
      </div>

      <WorkflowExecutionHistory workflowId={workflowId} />
    </div>
  );
}
