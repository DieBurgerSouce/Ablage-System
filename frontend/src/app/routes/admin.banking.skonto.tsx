import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const SkontoPage = lazy(() => import('@/features/banking/components/skonto/SkontoPage').then(m => ({ default: m.SkontoPage })));

export const Route = createFileRoute('/admin/banking/skonto')({
    component: LazySkontoPage,
});

function LazySkontoPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <SkontoPage />
        </Suspense>
    );
}
