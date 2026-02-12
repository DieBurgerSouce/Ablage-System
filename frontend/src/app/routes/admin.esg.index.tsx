/**
 * ESG Dashboard - Index Route
 *
 * Zeigt das ESG-Dashboard mit Übersichtskennzahlen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { ESGDashboard } from '@/features/esg';

export const Route = createFileRoute('/admin/esg/')({
    component: ESGDashboardPage,
});

function ESGDashboardPage() {
    return <ESGDashboard />;
}
