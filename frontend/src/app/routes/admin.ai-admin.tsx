import { createFileRoute } from '@tanstack/react-router';
import { AIAdminPage } from '@/features/ai-admin';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';

export const Route = createFileRoute('/admin/ai-admin')({
  component: AIAdminRoute,
});

function AIAdminRoute() {
  return (
    <UnifiedErrorBoundary context="general" variant="card">
      <AIAdminPage />
    </UnifiedErrorBoundary>
  );
}
