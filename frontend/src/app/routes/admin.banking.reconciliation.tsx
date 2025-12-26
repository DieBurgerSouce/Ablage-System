import { createFileRoute } from '@tanstack/react-router';
import { ReconciliationPage } from '@/features/banking/components/reconciliation/ReconciliationPage';

export const Route = createFileRoute('/admin/banking/reconciliation')({
    component: ReconciliationPage,
});
