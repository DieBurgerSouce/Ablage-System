import { createFileRoute } from '@tanstack/react-router';
import { SkontoPage } from '@/features/banking/components/skonto/SkontoPage';

export const Route = createFileRoute('/admin/banking/skonto')({
    component: SkontoPage,
});
