import { createFileRoute } from '@tanstack/react-router';
import { WorkflowMonitor } from '@/features/admin/workflows/WorkflowMonitor';

export const Route = createFileRoute('/admin/workflows/monitor')({
  component: WorkflowMonitor,
});
