/**
 * Cash-Flow Widget für Dashboard
 * Zeigt Liquiditätsprognose als kompakten Chart
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary für graceful degradation
 * - Konsistente Fehlerbehandlung mit anderen Widgets
 * - Real-time Updates via WebSocket (Phase 4.7)
 */

import { CashFlowChart } from '@/features/banking/components/CashFlowChart';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';
import { useWidgetSubscription } from '@/hooks/use-widget-subscription';

export function CashFlowWidget() {
    // Real-time Widget Updates (Phase 4.7)
    // Automatische Query-Invalidation bei Server-seitigen Aenderungen
    useWidgetSubscription('cashflow', {
        debounceMs: 500,
        autoInvalidate: true,
        queryKeysToInvalidate: [['cashflow'], ['finance'], ['banking']],
    });

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
