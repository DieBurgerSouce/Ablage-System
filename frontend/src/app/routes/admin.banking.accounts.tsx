import { createFileRoute } from '@tanstack/react-router';
import { AccountsPage } from '@/features/banking/components/accounts/AccountsPage';

export const Route = createFileRoute('/admin/banking/accounts')({
    component: AccountsPage,
});
