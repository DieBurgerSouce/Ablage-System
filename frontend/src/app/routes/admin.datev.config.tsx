/**
 * DATEV Konfiguration - Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { ConfigPage } from '@/features/datev/components/config';

export const Route = createFileRoute('/admin/datev/config')({
    component: ConfigPage,
});
