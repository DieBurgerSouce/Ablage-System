/**
 * Holding Reconciliation Route
 *
 * Intercompany-Abstimmung und Konsolidierung.
 * Feature 15: Intercompany Reconciliation UI
 */

import { createFileRoute } from '@tanstack/react-router';
import { IntercompanyReconciliation } from '@/features/holding/IntercompanyReconciliation';

export const Route = createFileRoute('/holding/reconciliation')({
    component: ReconciliationPage,
});

function ReconciliationPage() {
    return (
        <div className="container py-6">
            <IntercompanyReconciliation />
        </div>
    );
}
