import { createFileRoute } from '@tanstack/react-router';
import { lazyRoute } from '@/lib/lazyRoute';

const ImportPage = lazyRoute(() => import('@/features/banking/components/import/ImportPage').then(m => ({ default: m.ImportPage })));

export const Route = createFileRoute('/admin/banking/import')({
    component: LazyImportPage,
});

function LazyImportPage() {
    return <ImportPage />;
}
