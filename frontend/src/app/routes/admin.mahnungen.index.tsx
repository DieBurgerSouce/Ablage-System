/**
 * Admin Mahnungen Index (Übersicht)
 *
 * Zeigt das Mahnungs-Dashboard mit allen aktiven Mahnvorgängen
 */

import { createFileRoute } from '@tanstack/react-router';
import { DunningList } from '@/features/banking/components/DunningList';

export const Route = createFileRoute('/admin/mahnungen/')({
    component: MahnungenOverviewPage,
});

function MahnungenOverviewPage() {
    return <DunningList />;
}
