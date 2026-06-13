import { createFileRoute } from '@tanstack/react-router';
import { lazyRoute } from '@/lib/lazyRoute';

const TransactionsPage = lazyRoute(() => import('@/features/banking/components/transactions/TransactionsPage').then(m => ({ default: m.TransactionsPage })));

export const Route = createFileRoute('/admin/banking/transactions')({
    component: LazyTransactionsPage,
});

function LazyTransactionsPage() {
    return <TransactionsPage />;
}
