import { createFileRoute } from '@tanstack/react-router';
import { BankingDashboard } from '@/features/banking/components/BankingDashboard';

export const Route = createFileRoute('/admin/banking')({
    component: BankingPage,
});

function BankingPage() {
    return (
        <div className="max-w-7xl mx-auto p-8 space-y-8">
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-display">Banking & Finanzen</h1>
                <p className="text-muted-foreground mt-2">
                    Cash-Flow-Prognose, Altersanalyse und Mahnwesen auf einen Blick.
                </p>
            </div>

            <BankingDashboard />
        </div>
    );
}
