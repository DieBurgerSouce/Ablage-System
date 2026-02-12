import { createFileRoute } from '@tanstack/react-router';
import { ApprovalInbox } from '@/features/workflows/components/ApprovalInbox';
import { AnimatedPage } from '@/components/animations';

function ApprovalsPage() {
  return (
    <AnimatedPage>
      <ApprovalInbox />
    </AnimatedPage>
  );
}

export const Route = createFileRoute('/approvals')({
  component: ApprovalsPage,
});
