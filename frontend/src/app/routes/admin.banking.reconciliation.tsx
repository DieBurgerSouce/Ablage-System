import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const ReconciliationPage = lazy(() => import('@/features/banking/components/reconciliation/ReconciliationPage').then(m => ({ default: m.ReconciliationPage })));

export const Route = createFileRoute('/admin/banking/reconciliation')({
    component: LazyReconciliationPage,
});

function LazyReconciliationPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <ReconciliationPage />
        </Suspense>
    );
}
