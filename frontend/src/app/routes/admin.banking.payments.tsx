import { createFileRoute } from '@tanstack/react-router';
import { PaymentsPage } from '@/features/banking/components/payments/PaymentsPage';

export const Route = createFileRoute('/admin/banking/payments')({
    component: PaymentsPage,
});
