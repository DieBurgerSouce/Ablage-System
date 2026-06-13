import { createFileRoute } from '@tanstack/react-router';
import { lazyRoute } from '@/lib/lazyRoute';

const ReconciliationPage = lazyRoute(() => import('@/features/banking/components/reconciliation/ReconciliationPage').then(m => ({ default: m.ReconciliationPage })));

export const Route = createFileRoute('/admin/banking/reconciliation')({
    component: LazyReconciliationPage,
});

function LazyReconciliationPage() {
    return <ReconciliationPage />;
}
