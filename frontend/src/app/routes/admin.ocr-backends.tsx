import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const OCRBackendsPageContent = lazy(() => import('@/features/ocr-training/components/OCRBackendsPageContent').then(m => ({ default: m.OCRBackendsPageContent })));

export const Route = createFileRoute('/admin/ocr-backends')({
    component: OCRBackendsPage,
});

function OCRBackendsPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <OCRBackendsPageContent />
        </Suspense>
    );
}
