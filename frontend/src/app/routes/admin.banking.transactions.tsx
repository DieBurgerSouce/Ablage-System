import { createFileRoute } from '@tanstack/react-router';
import { TransactionsPage } from '@/features/banking/components/transactions/TransactionsPage';

export const Route = createFileRoute('/admin/banking/transactions')({
    component: TransactionsPage,
});
