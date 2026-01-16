/**
 * Cash-Flow Widget für Dashboard
 * Zeigt Liquiditätsprognose als kompakten Chart
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary für graceful degradation
 * - Konsistente Fehlerbehandlung mit anderen Widgets
 */

import { CashFlowChart } from '@/features/banking/components/CashFlowChart';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';

export function CashFlowWidget() {
    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Cash-Flow" />}
            errorTitle="Cash-Flow Fehler"
            errorDescription="Die Liquiditätsprognose konnte nicht geladen werden."
        >
            <section aria-labelledby="cashflow-heading">
                <h2 id="cashflow-heading" className="sr-only">Cash-Flow Prognose</h2>
                <CashFlowChart
                    defaultDays={14}
                    showControls={false}
                />
            </section>
        </ErrorBoundary>
    );
}
