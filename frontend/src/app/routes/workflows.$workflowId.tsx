/**
 * Workflow Detail/Editor Route
 *
 * Seite zum Bearbeiten eines bestehenden Workflows.
 */

import { createFileRoute } from '@tanstack/react-router';
import { WorkflowBuilder } from '@/features/workflows';
import { useWorkflow } from '@/features/workflows';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Link } from '@tanstack/react-router';

export const Route = createFileRoute('/workflows/$workflowId')({
  component: WorkflowDetailPage,
});

function WorkflowDetailPage() {
  const { workflowId } = Route.useParams();
  const { data: workflow, isLoading, error } = useWorkflow(workflowId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-[600px] w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Fehler beim Laden</AlertTitle>
        <AlertDescription>
          Der Workflow konnte nicht geladen werden.
          <Button variant="link" asChild className="ml-2">
            <Link to="/workflows">Zurück zur Übersicht</Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (!workflow) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Nicht gefunden</AlertTitle>
        <AlertDescription>
          Der angeforderte Workflow existiert nicht.
          <Button variant="link" asChild className="ml-2">
            <Link to="/workflows">Zurück zur Übersicht</Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{workflow.name}</h1>
        {workflow.description && (
          <p className="text-muted-foreground">{workflow.description}</p>
        )}
      </div>

      <WorkflowBuilder workflow={workflow} />
    </div>
  );
}
