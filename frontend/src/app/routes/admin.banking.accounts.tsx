import { createFileRoute } from '@tanstack/react-router';
import { lazy, Suspense } from 'react';
import { LazyLoadFallback } from '@/components/LazyLoadFallback';

const AccountsPage = lazy(() => import('@/features/banking/components/accounts/AccountsPage').then(m => ({ default: m.AccountsPage })));

export const Route = createFileRoute('/admin/banking/accounts')({
    component: LazyAccountsPage,
});

function LazyAccountsPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <AccountsPage />
        </Suspense>
    );
}
