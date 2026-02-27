import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const PaymentsPage = lazy(() => import('@/features/banking/components/payments/PaymentsPage').then(m => ({ default: m.PaymentsPage })));

export const Route = createFileRoute('/admin/banking/payments')({
    component: LazyPaymentsPage,
});

function LazyPaymentsPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <PaymentsPage />
        </Suspense>
    );
}
