/**
 * Aging Report Widget für Dashboard
 * Zeigt Fälligkeitsstruktur als Balkendiagramm
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary für graceful degradation
 * - Konsistente Fehlerbehandlung mit anderen Widgets
 */

import { AgingBucketChart } from '@/features/banking/components/AgingBucketChart';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { DashboardSectionError } from '../shared';

export function AgingReportWidget() {
    return (
        <ErrorBoundary
            fallback={<DashboardSectionError section="Fälligkeitsstruktur" />}
            errorTitle="Fälligkeitsstruktur Fehler"
            errorDescription="Die Fälligkeitsübersicht konnte nicht geladen werden."
        >
            <section aria-labelledby="aging-heading">
                <h2 id="aging-heading" className="sr-only">Fälligkeitsstruktur</h2>
                <AgingBucketChart />
            </section>
        </ErrorBoundary>
    );
}
