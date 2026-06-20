import { createFileRoute } from '@tanstack/react-router';
import { lazyRoute } from '@/lib/lazyRoute';

const PaymentsPage = lazyRoute(() => import('@/features/banking/components/payments/PaymentsPage').then(m => ({ default: m.PaymentsPage })));

export const Route = createFileRoute('/admin/banking/payments')({
    component: LazyPaymentsPage,
});

function LazyPaymentsPage() {
    return <PaymentsPage />;
}
