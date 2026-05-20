/**
 * DATEV Connect - Buchungen Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { BuchungenPage } from '@/features/datev/components/connect';

export const Route = createFileRoute('/admin/datev-connect/buchungen')({
    component: BuchungenPage,
});
