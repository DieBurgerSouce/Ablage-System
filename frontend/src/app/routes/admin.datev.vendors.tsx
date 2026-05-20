/**
 * DATEV Lieferanten-Zuordnungen - Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { VendorsPage } from '@/features/datev/components/vendors';

export const Route = createFileRoute('/admin/datev/vendors')({
    component: VendorsPage,
});
