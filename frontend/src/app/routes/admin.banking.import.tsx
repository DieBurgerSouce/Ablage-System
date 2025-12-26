import { createFileRoute } from '@tanstack/react-router';
import { ImportPage } from '@/features/banking/components/import/ImportPage';

export const Route = createFileRoute('/admin/banking/import')({
    component: ImportPage,
});
