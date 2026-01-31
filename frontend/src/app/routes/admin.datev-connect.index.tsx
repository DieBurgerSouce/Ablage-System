/**
 * DATEV Connect - Verbindungen (Index Route)
 */

import { createFileRoute } from '@tanstack/react-router';
import { ConnectionsPage } from '@/features/datev/components/connect';

export const Route = createFileRoute('/admin/datev-connect/')({
    component: ConnectionsPage,
});
