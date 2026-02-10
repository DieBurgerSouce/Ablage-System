/**
 * Workflow Execution Page
 *
 * Seite zur Anzeige einer Workflow-Ausfuehrung mit Visualisierung und Timeline.
 */

import { useParams } from '@tanstack/react-router';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useNavigate } from '@tanstack/react-router';
import WorkflowExecutionViewer from './WorkflowExecutionViewer';
import ExecutionTimeline from './ExecutionTimeline';

export default function WorkflowExecutionPage() {
  const navigate = useNavigate();
  const { executionId } = useParams({ strict: false }) as { executionId?: string };

  if (!executionId) {
    return (
      <div className="container py-8">
        <div className="text-center">
          <p className="text-lg text-muted-foreground">
            Keine Ausfuehrungs-ID angegeben
          </p>
          <Button onClick={() => navigate({ to: '/workflows' })} className="mt-4">
            Zurück zu Workflows
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="container py-8">
      {/* Header mit Zurück-Button */}
      <div className="mb-6">
        <Button
          variant="ghost"
          onClick={() => navigate({ to: '/workflows' })}
          className="mb-4"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Zurück zu Workflows
        </Button>
      </div>

      {/* Layout: Visualization + Timeline */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Hauptbereich: Workflow Visualization */}
        <div className="lg:col-span-2">
          <WorkflowExecutionViewer executionId={executionId} />
        </div>

        {/* Seitenleiste: Timeline */}
        <div className="lg:col-span-1">
          <ExecutionTimeline executionId={executionId} />
        </div>
      </div>
    </div>
  );
}
