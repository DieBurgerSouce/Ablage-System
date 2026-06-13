import { createFileRoute } from '@tanstack/react-router';
import { lazyRoute } from '@/lib/lazyRoute';

const OCRBackendsPageContent = lazyRoute(() => import('@/features/ocr-training/components/OCRBackendsPageContent').then(m => ({ default: m.OCRBackendsPageContent })));

export const Route = createFileRoute('/admin/ocr-backends')({
    component: OCRBackendsPage,
});

function OCRBackendsPage() {
    return <OCRBackendsPageContent />;
}
