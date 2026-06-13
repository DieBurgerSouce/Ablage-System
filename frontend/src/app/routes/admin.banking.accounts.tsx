import { createFileRoute } from '@tanstack/react-router';
import { lazyRoute } from '@/lib/lazyRoute';

const AccountsPage = lazyRoute(() => import('@/features/banking/components/accounts/AccountsPage').then(m => ({ default: m.AccountsPage })));

export const Route = createFileRoute('/admin/banking/accounts')({
    component: LazyAccountsPage,
});

function LazyAccountsPage() {
    return <AccountsPage />;
}
