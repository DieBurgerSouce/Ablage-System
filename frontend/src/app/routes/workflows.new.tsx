/**
 * New Workflow Route
 *
 * Seite zum Erstellen eines neuen Workflows.
 */

import { createFileRoute } from '@tanstack/react-router';
import { WorkflowBuilder, WorkflowTemplates } from '@/features/workflows';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Plus, Layout } from 'lucide-react';

export const Route = createFileRoute('/workflows/new')({
  component: NewWorkflowPage,
});

function NewWorkflowPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Neuer Workflow</h1>
        <p className="text-muted-foreground">
          Erstellen Sie einen neuen Workflow von Grund auf oder waehlen Sie ein Template.
        </p>
      </div>

      <Tabs defaultValue="templates" className="space-y-6">
        <TabsList>
          <TabsTrigger value="templates" className="gap-2">
            <Layout className="h-4 w-4" />
            Templates
          </TabsTrigger>
          <TabsTrigger value="builder" className="gap-2">
            <Plus className="h-4 w-4" />
            Leerer Workflow
          </TabsTrigger>
        </TabsList>

        <TabsContent value="templates">
          <WorkflowTemplates />
        </TabsContent>

        <TabsContent value="builder">
          <WorkflowBuilder />
        </TabsContent>
      </Tabs>
    </div>
  );
}
