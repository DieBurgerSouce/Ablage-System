import { createFileRoute } from '@tanstack/react-router';
import { WorkflowRuleBuilder } from '@/features/admin/workflows/WorkflowRuleBuilder';

export const Route = createFileRoute('/admin/workflows')({
  component: WorkflowRuleBuilder,
});
