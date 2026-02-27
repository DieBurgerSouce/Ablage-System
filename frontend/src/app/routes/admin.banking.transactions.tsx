import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const TransactionsPage = lazy(() => import('@/features/banking/components/transactions/TransactionsPage').then(m => ({ default: m.TransactionsPage })));

export const Route = createFileRoute('/admin/banking/transactions')({
    component: LazyTransactionsPage,
});

function LazyTransactionsPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <TransactionsPage />
        </Suspense>
    );
}
