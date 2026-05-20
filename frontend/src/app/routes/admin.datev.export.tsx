/**
 * DATEV Export - Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { ExportPage } from '@/features/datev/components/export';

export const Route = createFileRoute('/admin/datev/export')({
    component: ExportPage,
});
