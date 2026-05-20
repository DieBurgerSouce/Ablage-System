import { createFileRoute } from '@tanstack/react-router';
import { KanbanBoard } from '@/features/kanban/components/KanbanBoard';

export const Route = createFileRoute('/admin/kanban')({
  component: KanbanPage,
});

function KanbanPage() {
  return (
    <div className="container mx-auto py-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Kanban Board</h1>
          <p className="text-muted-foreground">Dokumenten-Workflow verwalten</p>
        </div>
      </div>
      <KanbanBoard workflowType="document" />
    </div>
  );
}
