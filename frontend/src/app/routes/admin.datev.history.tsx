/**
 * DATEV Export-Historie - Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { HistoryPage } from '@/features/datev/components/history';

export const Route = createFileRoute('/admin/datev/history')({
    component: HistoryPage,
});
