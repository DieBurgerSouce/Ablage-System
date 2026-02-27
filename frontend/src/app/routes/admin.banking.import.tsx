import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const ImportPage = lazy(() => import('@/features/banking/components/import/ImportPage').then(m => ({ default: m.ImportPage })));

export const Route = createFileRoute('/admin/banking/import')({
    component: LazyImportPage,
});

function LazyImportPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <ImportPage />
        </Suspense>
    );
}
