import { createFileRoute } from '@tanstack/react-router';
import { BankingOverview } from '@/features/banking/components/overview';

export const Route = createFileRoute('/admin/banking/')({
    component: BankingOverviewPage,
});

function BankingOverviewPage() {
    return <BankingOverview />;
}
