/**
 * DATEV Connect - KI-Kontierung Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { KontierungPage } from '@/features/datev/components/connect';

export const Route = createFileRoute('/admin/datev-connect/kontierung')({
    component: KontierungPage,
});
