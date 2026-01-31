/**
 * DATEV Connect - Sync Status Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { SyncStatusPage } from '@/features/datev/components/connect';

export const Route = createFileRoute('/admin/datev-connect/sync')({
    component: SyncStatusPage,
});
